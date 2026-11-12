"""Zotero-backed reference metadata and project bibliography associations.

The Zotero local API is tried first.  When it is unavailable this module opens
the local database through SQLite's immutable/read-only URI.  It never launches
Zotero, changes its settings, or writes its database. Local PDF text is read only on an explicit extraction request.
Project association receipts and BibTeX entries live in the project instead.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from contextlib import contextmanager
from typing import Any

_JSON = "application/json; charset=utf-8"
_DB = Path(os.environ.get("LAPLACE_ZOTERO_DB", "/home/phujck/Zotero/zotero.sqlite"))
_API = os.environ.get("LAPLACE_ZOTERO_API", "http://127.0.0.1:23119/api").rstrip("/")
_ASSOCIATIONS = "references.json"
_KEY = re.compile(r"^[A-Za-z0-9]{8}$")
_CITEKEY = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")
_BIBKEY = re.compile(r"^[ \t]*@\s*[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
_BIB_CMD = re.compile(r"\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_BIB_TYPES = {"journalArticle": "article", "book": "book", "bookSection": "incollection",
              "conferencePaper": "inproceedings", "thesis": "phdthesis", "webpage": "misc",
              "preprint": "misc", "unpublished": "unpublished"}
_DOI = re.compile(r"^10\.\S+/.+", re.I)
_CITE = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")


def _root() -> Path:
    return source_tree()


def _response(status: int, payload: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _q1(query: dict, name: str) -> str:
    value = query.get(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return value.strip() if isinstance(value, str) else ""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _api_get(path: str, params: dict[str, str] | None = None) -> Any:
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    with urllib.request.urlopen(_API + path + query, timeout=0.35) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_item(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    key = data.get("key") or raw.get("key")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return None
    creators = data.get("creators") if isinstance(data.get("creators"), list) else []
    names = [" ".join(str(c.get(k) or "") for k in ("firstName", "lastName")).strip()
             for c in creators if isinstance(c, dict)]
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    collections = data.get("collections") if isinstance(data.get("collections"), list) else []
    publication = {name:data.get(source,"") for name,source in {'publication_title':'publicationTitle','volume':'volume','issue':'issue','pages':'pages','publisher':'publisher','place':'place','isbn':'ISBN'}.items()}
    return {**publication, "key": key, "version": str(data.get("version") or raw.get("version") or ""),
            "modified": str(data.get("dateModified") or ""), "item_type": data.get("itemType", ""),
            "title": data.get("title", ""), "creators": [n for n in names if n],
            "year": str(data.get("date") or "")[:4], "doi": data.get("DOI", ""),
            "url": data.get("url", ""), "collections": collections, "attachments": attachments,
            "citation_key": data.get("citationKey") or f"zotero_{key.lower()}",
            "deep_link": f"zotero://select/library/items/{key}"}


class _SQLite:
    def __init__(self, path: Path = _DB):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        return sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)

    def status(self) -> dict:
        with self._connect() as con:
            total = con.execute("SELECT count(*) FROM items").fetchone()[0]
            types = con.execute("SELECT t.typeName,count(*) FROM items i JOIN itemTypes t ON t.itemTypeID=i.itemTypeID GROUP BY t.typeName ORDER BY t.typeName").fetchall()
        return {"provider": "sqlite", "database": "available", "item_count": total,
                "item_type_count": len(types), "schema": "items,itemData,itemDataValues,creators,collections,itemAttachments"}

    def _items(self, where: str, values: tuple[Any, ...], limit: int = 30) -> list[dict]:
        sql = """SELECT i.itemID,i.key,i.version,i.dateModified,t.typeName
                 FROM items i JOIN itemTypes t ON t.itemTypeID=i.itemTypeID
                 WHERE t.typeName NOT IN ('attachment','note','annotation') AND """ + where + " ORDER BY i.itemID DESC LIMIT ?"
        with self._connect() as con:
            base = con.execute(sql, values + (limit,)).fetchall()
            return [self._detail(con, *row) for row in base]

    def _detail(self, con: sqlite3.Connection, item_id: int, key: str, version: Any, modified: Any, item_type: str) -> dict:
        fields = dict(con.execute("""SELECT f.fieldName,v.value FROM itemData d
            JOIN fields f ON f.fieldID=d.fieldID JOIN itemDataValues v ON v.valueID=d.valueID
            WHERE d.itemID=?""", (item_id,)).fetchall())
        creators = [" ".join(x for x in row if x) for row in con.execute("""SELECT c.firstName,c.lastName
            FROM itemCreators ic JOIN creators c ON c.creatorID=ic.creatorID WHERE ic.itemID=? ORDER BY ic.orderIndex""", (item_id,))]
        collections = [row[0] for row in con.execute("""SELECT c.collectionName FROM collectionItems ci
            JOIN collections c ON c.collectionID=ci.collectionID WHERE ci.itemID=? ORDER BY c.collectionName""", (item_id,))]
        attachments = [{"key": row[0], "content_type": row[1], "path": row[2]}
                       for row in con.execute("""SELECT i.key,a.contentType,a.path FROM itemAttachments a
                           JOIN items i ON i.itemID=a.itemID WHERE a.parentItemID=?""", (item_id,))]
        publication = {name:fields.get(source,"") for name,source in {'publication_title':'publicationTitle','volume':'volume','issue':'issue','pages':'pages','publisher':'publisher','place':'place','isbn':'ISBN'}.items()}
        return {**publication,"key": key, "version": str(version or ""), "modified": str(modified or ""),
                "item_type": item_type, "title": fields.get("title", ""), "creators": creators,
                "year": str(fields.get("date", ""))[:4], "doi": fields.get("DOI", ""), "url": fields.get("url", ""),
                "collections": collections, "attachments": attachments,
                "citation_key": f"zotero_{key.lower()}", "deep_link": f"zotero://select/library/items/{key}"}

    def search(self, text: str) -> list[dict]:
        pattern = "%" + text.replace("%", "\\%").replace("_", "\\_") + "%"
        return self._items("""i.itemID IN (
            SELECT d.itemID FROM itemData d JOIN itemDataValues v ON v.valueID=d.valueID WHERE v.value LIKE ? ESCAPE '\\'
            UNION SELECT ic.itemID FROM itemCreators ic JOIN creators c ON c.creatorID=ic.creatorID
                  WHERE (c.firstName || ' ' || c.lastName) LIKE ? ESCAPE '\\'
            UNION SELECT ci.itemID FROM collectionItems ci JOIN collections c ON c.collectionID=ci.collectionID
                  WHERE c.collectionName LIKE ? ESCAPE '\\')""", (pattern, pattern, pattern))

    def item(self, key: str) -> dict | None:
        found = self._items("i.key=?", (key,), 1)
        return found[0] if found else None


class Library:
    """API-first adapter with a local, read-only Zotero fallback."""
    def __init__(self, sqlite_path: Path = _DB):
        self.sqlite = _SQLite(sqlite_path)

    def _api_items(self, path: str, params: dict[str, str] | None = None) -> list[dict] | None:
        try:
            raw = _api_get(path, params)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        rows = raw if isinstance(raw, list) else [raw]
        items = [_api_item(row) for row in rows]
        return [item for item in items if item]

    def status(self) -> dict:
        try:
            _api_get("/status")
            return {"provider": "api", "api": "available", "database": "not-read"}
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            try:
                out = self.sqlite.status(); out["api"] = "unavailable"; return out
            except FileNotFoundError:
                return {"provider": "unavailable", "api": "unavailable", "database": "missing"}

    def search(self, text: str) -> tuple[str, list[dict]]:
        items = self._api_items("/items", {"q": text, "limit": "30"})
        return ("api", items) if items is not None else ("sqlite", self.sqlite.search(text))

    def item(self, key: str) -> tuple[str, dict | None]:
        items = self._api_items("/items/" + urllib.parse.quote(key, safe=""))
        return ("api", items[0] if items else None) if items is not None else ("sqlite", self.sqlite.item(key))

def _attachment(library: Library, item: dict) -> Path | None:
    for att in item.get('attachments') or []:
        if not isinstance(att, dict) or 'pdf' not in str(att.get('content_type','')).lower(): continue
        raw=str(att.get('path') or ''); key=str(att.get('key') or '')
        if raw.startswith('storage:') and _KEY.fullmatch(key):
            home=(library.sqlite.path.parent/'storage'/key).resolve()
            path=(home/raw.removeprefix('storage:')).resolve()
            if path.is_relative_to(home) and path.suffix.lower()=='.pdf' and path.is_file(): return path
    return None

def extract_text(key: str, library: Library | None=None, limit: int=24000, offset: int=0) -> dict:
    if not isinstance(offset,int) or not 0 <= offset <= 20_000_000 or not isinstance(limit,int) or not 1000 <= limit <= 48000:
        raise ValueError('Use a nonnegative character offset and a limit from 1000 to 48000.')
    library=library or Library(); provider,item=library.item(key)
    if not item: raise ValueError('item not found')
    pdf=_attachment(library,item)
    if pdf is None and provider=='api':
        # Item metadata endpoints do not necessarily embed child attachments.
        local=library.sqlite.item(key)
        if local:
            item={**item,'attachments':local.get('attachments',[])}
            pdf=_attachment(library,item)
    if pdf is None: return {'provider':provider,'item':item,'source_state':'metadata-only','reason':'no local PDF attachment'}
    tool=shutil.which('pdftotext')
    if not tool: return {'provider':provider,'item':item,'source_state':'metadata-only','reason':'pdftotext unavailable'}
    run=subprocess.run([tool,str(pdf),'-'],capture_output=True,text=True,timeout=20)
    if run.returncode:
        return {'provider':provider,'item':item,'source_state':'extraction-failed','reason':run.stderr[-1200:] or 'PDF text extraction failed'}
    text=run.stdout[offset:offset+limit]
    attachment_key=next((a.get('key') for a in item.get('attachments',[]) if isinstance(a,dict) and _KEY.fullmatch(str(a.get('key') or '')) and pdf.is_relative_to((library.sqlite.path.parent/'storage'/a['key']).resolve())),None)
    return {'provider':provider,'item':item,'source_state':'extracted','attachment':{'sha256':_sha256_file(pdf),'key':attachment_key},'text':text,'truncated':len(run.stdout)>offset+limit,'offset':offset,'next_offset':offset+len(text) if len(run.stdout)>offset+limit else None,'total_characters':len(run.stdout),'page_start':run.stdout[:offset].count('\f')+1,'page_end':run.stdout[:offset+len(text)].count('\f')+1,'char_limit':limit,'citation_note':'Use the source text and page breaks to verify quotations; metadata and attachment presence do not prove a claim.'}

def _sha256_file(path: Path) -> str:
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def _manuscript(project: str, root: Path) -> Path | None:
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("status") == "resolved" and source.get("manuscript_dir"):
        candidate = Path(manuscript_source.project_state_dir(source, root))  # reference associations are project state
        return candidate if candidate.is_absolute() else root / candidate
    from laplace.pipeline import registry
    item = registry.resolve(project, root)
    return item.path(item.manuscript_dir, root) if item and item.manuscript_dir else None


def _bibliography_names(main: Path) -> list[str]:
    """Consumers from the selected include tree, relative to its compile root."""
    from laplace.manuscript import manuscript_source
    names = []
    for source in manuscript_source.traversal(main, repo_root=main.parent).get('sources', []):
        text = re.sub(r"(?<!\\)%[^\n]*", '', str(source.get('text') or ''))
        for match in _BIB_CMD.finditer(text):
            names.extend(name.strip() for name in match.group(1).split(',') if name.strip())
    return list(dict.fromkeys(names))


def _bib_path(manuscript: Path, selected: Path | None = None) -> Path:
    main = selected or manuscript / "main.tex"
    names = _bibliography_names(main)
    name = names[0] if names else 'refs'
    return main.parent / (name if name.endswith(".bib") else name + ".bib")


def _load_associations(manuscript: Path, *, require_supported: bool = False) -> list[dict]:
    path = manuscript / _ASSOCIATIONS
    try: raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: return []
    except (OSError, ValueError) as exc: raise ValueError("The reference association file is unreadable; it was preserved.") from exc
    if require_supported and (not isinstance(raw, dict)
            or raw.get("schema_version", "laplace.references/1") != "laplace.references/1"
            or not isinstance(raw.get("associations", []), list)
            or any(not isinstance(row, dict) for row in raw.get("associations", []))):
        raise ValueError("The existing reference association shape is unsupported; it was preserved. Inspect its custody before importing a source.")
    return [dict(row) for row in raw.get("associations", []) if isinstance(row, dict)] if isinstance(raw, dict) else []


def _write_associations(manuscript: Path, rows: list[dict]) -> None:
    target = manuscript / _ASSOCIATIONS
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps({"schema_version": "laplace.references/1", "associations": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)


def _owned_file(root: Path, path: Path, before: bytes | None, after: bytes | None = None) -> dict:
    """Expected postimage, not an attribution of concurrent foreign writes."""
    current=path.read_bytes() if path.is_file() else None
    expected=current if after is None else after
    digest=lambda data:'sha256:'+hashlib.sha256(data).hexdigest() if data is not None else None
    return {'scope':'repository','path':str(path.resolve().relative_to(root.resolve())),
            'before_sha256':digest(before),'after_sha256':digest(expected),
            'observed_after_sha256':digest(current)}

def _association_bytes(rows: list[dict]) -> bytes:
    return (json.dumps({'schema_version':'laplace.references/1','associations':rows},indent=2,sort_keys=True)+'\n').encode('utf-8')

def _owned_associations(root,manuscript,before_bytes,before_rows,rows,views=()):
    prior={(row.get('key'),row.get('claim_id')):row for row in before_rows}
    after={(row.get('key'),row.get('claim_id')):row for row in rows};objects=[]
    for identity in dict.fromkeys([*prior,*after]):
        old,new=prior.get(identity),after.get(identity)
        if old==new:continue
        objects.append({'owner':'references','id':str(identity[0])+'|'+str(identity[1] or ''),'key':identity[0],'claim_id':identity[1],
            'before_revision':'sha256:'+_digest(old) if old is not None else None,'after_revision':'sha256:'+_digest(new) if new is not None else None})
    file=_owned_file(root,manuscript/_ASSOCIATIONS,before_bytes,_association_bytes(rows))
    return {'schema_version':'laplace.owner-mutation/1','files':[file] if file['before_sha256']!=file['after_sha256'] else [],'objects':objects,'rewire_records':[],'views':list(views)}


def _bib_escape(value: Any) -> str:
    chars = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
             "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    return "".join(chars.get(char, " " if char in "\r\n\t" else char)
                   for char in str(value))


def _metadata(item: dict) -> dict:
    keys = ("key", "version", "modified", "item_type", "title", "creators", "year", "doi", "url",
            "publication_title", "volume", "issue", "pages", "publisher", "place", "isbn", "provenance", "fulltext_urls")
    return {key: item.get(key) for key in keys if item.get(key) not in (None, "", [])}


def _bib_entries(text: str) -> list[dict]:
    matches = list(_BIBKEY.finditer(text))
    entries = []
    for index, match in enumerate(matches):
        # The regexp ends just after the entry's opening ``{key,``.  Scan to
        # its balanced closing brace instead of assigning intervening comments
        # and whitespace to this entry; update must replace exactly one entry.
        depth, escaped, comment, end = 1, False, False, None
        ceiling = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        for offset in range(match.end(), ceiling):
            char = text[offset]
            if comment:
                if char in "\r\n":
                    comment = False
                continue
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == "%":
                comment = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = offset + 1
                    break
        end = end if end is not None else ceiling
        entries.append({"key": match.group(1), "start": match.start(), "end": end,
                        "closed": depth == 0, "text": text[match.start():end]})
    return entries


def _entry_matches(entry: str, key: str, dois: set[str]) -> bool:
    if re.search(r"(?:zotero_key|laplace_key)\s*=\s*\{" + re.escape(_bib_escape(key)) + r"\}", entry, re.I):
        return True
    found = re.search(r'doi\s*=\s*(?:\{([^}]+)\}|"([^"]+)")', entry, re.I)
    normalize = lambda value: re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value).strip(), flags=re.I).lower().replace(r'\_', '_')
    return bool(found and normalize(found.group(1) or found.group(2)) in {normalize(value) for value in dois if value})



def _bib_entry(item: dict, citekey: str) -> str:
    fields = {"title": item.get("title", ""), "author": " and ".join(item.get("creators") or []),
              "year": item.get("year", ""), "doi": item.get("doi", ""), "url": item.get("url", ""),
              "zotero_key" if _KEY.fullmatch(str(item["key"])) else "laplace_key": item["key"]}
    for field,key in {'volume':'volume','number':'issue','pages':'pages','publisher':'publisher','address':'place','isbn':'isbn'}.items():
        if item.get(key): fields[field]=item[key]
    if item.get('publication_title'):
        fields['journal' if item.get('item_type')=='journalArticle' else 'booktitle']=item['publication_title']
    body = "\n".join(f"  {name} = {{{_bib_escape(value)}}}," for name, value in fields.items() if value)
    entry_type = _BIB_TYPES.get(str(item.get("item_type") or ""), "misc")
    return f"@{entry_type}{{{citekey},\n{body}\n}}\n"

def _crossref(doi: str | None = None, query: str = "", rows: int = 10) -> list[dict]:
    if doi and not _DOI.fullmatch(doi): raise ValueError("DOI is invalid")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/") if doi else "https://api.crossref.org/works?" + urllib.parse.urlencode({"query":query,"rows":max(1,min(20,rows))})
    request=urllib.request.Request(url, headers={"User-Agent":"Laplace literature metadata/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response: message=json.loads(response.read().decode("utf-8")).get("message")
    return [message] if doi else list((message or {}).get("items") or [])

def _crossref_metadata(row: dict) -> dict:
    authors=[" ".join(x for x in (str(a.get("given") or ""),str(a.get("family") or "")) if x).strip() for a in row.get("author") or [] if isinstance(a,dict)]
    date=(row.get("published-print") or row.get("published-online") or row.get("issued") or {}).get("date-parts") or [[""]]
    return {"title":(row.get("title") or [""])[0],"creators":[x for x in authors if x],"year":str(date[0][0] if date and date[0] else ""),"doi":str(row.get("DOI") or "").lower(),"url":row.get("URL") or "","publication_title":(row.get("container-title") or [""])[0],"volume":row.get("volume") or "","issue":row.get("issue") or "","pages":row.get("page") or "","publisher":row.get("publisher") or "","item_type":{"journal-article":"journalArticle","book":"book","monograph":"book","book-chapter":"bookSection","proceedings-article":"conferencePaper","posted-content":"preprint"}.get(row.get("type"),"misc")}

def literature_discover(query: str, rows: int = 10, root: Path | None = None) -> dict:
    from laplace.research import literature
    local=literature.local_candidates(query,(root or _root()).resolve(),min(10,max(1,rows)))
    try:
        public=[_crossref_metadata(row) for row in _crossref(query=query,rows=rows)]
        return {'provider':'crossref','query':query,'local_candidates':local,'items':public,'public_state':'AVAILABLE','metadata_only':True}
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        return {'provider':'crossref','query':query,'local_candidates':local,'items':[],'public_state':'UNAVAILABLE','public_error':str(exc),'metadata_only':True}


def citation_spans(project: str, root: Path) -> tuple[dict, list[dict], dict]:
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve(project,repo_root=root)
    traversal=manuscript_source.traversal(source.get("root"),repo_root=root) if source.get("root") else {"sources":[]}
    spans=[]
    pattern = re.compile(r"\\(?:[a-zA-Z]*cite[a-zA-Z*]*|nocite)\s*(?:\[[^]]*\]\s*)*\{([^}]+)\}")
    for item in traversal.get("sources") or []:
        text=str(item.get("text") or "")
        # Mask comments without moving exact character offsets.
        from laplace.manuscript.proposal_preflight import _active_tex
        masked = _active_tex(text)
        for match in pattern.finditer(masked):
            line=text.count("\n",0,match.start())+1
            for cited in match.group(1).split(","):
                spans.append({"citekey":cited.strip(),"file":item.get("file"),"line_start":line,
                    "line_end":text.count("\n",0,match.end())+1,"character_start":match.start(),
                    "character_end":match.end(),"text":text[match.start():match.end()],
                    "source_sha256":item.get("sha256"),"instance":item.get("order")})
    return source, spans, traversal


def literature_uses(project: str, root: Path | None = None, key: str = "", claim_id: str = "", offset: int = 0, limit: int = 100, citation_offset: int = 0, citation_limit: int = 200) -> dict:
    root=(root or _root()).resolve(); manuscript=_manuscript(project,root)
    if manuscript is None:return {"project":project,"uses":[],"claim_sources":{},"source_claims":{}}
    source, spans, traversal = citation_spans(project, root)
    from laplace.research import literature
    stored_rows = _load_associations(manuscript)
    requested_key=key
    selected_item=None
    if key:
        _provider,selected_item=literature.resolve_item(project,key,root)
        if selected_item is not None:key=str(selected_item['key'])
    all_rows = list(stored_rows)
    mapped = {row.get('canonical_id'):row for row in all_rows if row.get('canonical_id') and row.get('citekey')}
    normalized = {}
    for row in all_rows:
        bibliography = mapped.get(row.get('canonical_id'))
        if bibliography and row.get('key') != bibliography.get('key'):
            row = {**row, **{field:bibliography.get(field) for field in ('key','citekey','metadata','bib_path','source')}}
        normalized[(row.get('key'),row.get('claim_id'))] = row
    all_rows = list(normalized.values())
    all_rows += literature.canonical_rows(project, root, all_rows)
    rows=[row for row in all_rows if (not key or row.get("key")==key) and (not claim_id or row.get("claim_id")==claim_id)]
    offset=max(0,int(offset)); limit=max(1,min(200,int(limit)))
    citation_offset=max(0,int(citation_offset)); citation_limit=max(1,min(500,int(citation_limit)))
    total=len(rows)
    # Independent pages refer to the same explicit query, not unrelated global
    # spans or only the associations on this page. Binding is not entailment.
    citation_keys=None
    if key or claim_id:
        citation_keys={str(row['citekey']) for row in rows if row.get('citekey')}
        # A claim query is the intersection with its authored bindings. An
        # unmatched claim cannot be bypassed by spelling the source's citekey.
        # Source-only reads also expose genuinely unbound registered/literal use.
        if requested_key and not claim_id:
            if selected_item:
                if selected_item.get('citation_key'):
                    citation_keys.add(str(selected_item['citation_key']))
            else:
                citation_keys.add(requested_key)
        spans=[span for span in spans if span['citekey'] in citation_keys]
    citation_total=len(spans)
    rows=rows[offset:offset+limit]; spans=spans[citation_offset:citation_offset+citation_limit]
    uses=[]; claim_sources={}; source_claims={}; support_cache={}
    from laplace.research import literature_support
    net=literature_support.network(project,root)
    main=Path(source.get('root') or '')
    if not main.is_absolute():main=root/main
    bib=_bib_path(manuscript,main) if main.is_file() else None
    entries={entry['key']:entry for entry in _bib_entries(bib.read_text(encoding='utf-8'))} if bib and bib.is_file() and bib.resolve().is_relative_to(root) else {}
    has_consumer=main.is_file() and bool(_bibliography_names(main))
    bib_revision=_sha256_file(bib) if bib and bib.is_file() and bib.resolve().is_relative_to(root) else None
    for row in rows:
        currentness = 'STALE' if row.get('state') == 'STALE' or (row.get('evidence_source_identity') and row['evidence_source_identity'] != (row.get('source') or {}).get('identity')) else 'CURRENT'
        if row.get('state') == 'UNVERIFIED': currentness = 'UNVERIFIED'
        if row.get('evidence_origin') == 'canonical typed relation' or (row.get('source') or {}).get('provider') == 'canonical': currentness = 'UNASSESSED'
        provenance = (row.get('metadata') or {}).get('provenance') or {}
        if provenance.get('path'):
            try:
                local = Path(provenance['path'])
                if not local.is_absolute(): local = root / local
                if _sha256_file(local) != provenance.get('sha256'): currentness = 'STALE'
            except OSError: currentness = 'UNVERIFIED'
        qualified=None
        if row.get('claim_id') and row.get('canonical_id'):
            claim=row['claim_id']
            if claim not in support_cache:support_cache[claim]=literature_support.for_node(project,claim,root,net=net,associations=stored_rows)
            qualified=next((source for source in support_cache[claim]['sources'] if source['source_id']==row['canonical_id']),None)
            if qualified:
                currentness={'PASSAGE_OBSERVED':'CURRENT','CLAIM_CHANGED':'STALE','STALE':'STALE','PENDING_CANONICAL':'UNVERIFIED'}.get(qualified['qualification'],'UNASSESSED')
        joined={**{field:value for field,value in row.items() if field!='reading_observations'},
                'reading_observation_count':len(row.get('reading_observations') or []),
                'bibliography':literature.bibliography_projection(project,root,row.get('citekey'),selected=source,entries=entries,has_consumer=has_consumer,bib_revision=bib_revision),
                "source_qualification":qualified.get('qualification') if qualified else None,"manuscript_uses":[span for span in spans if span["citekey"]==row.get("citekey")],
                "evidence_currentness":currentness,"evidence_status":row.get("evidence_status","metadata-only")}
        uses.append(joined)
        if row.get('claim_id'):
            relation={k:joined.get(k) for k in ('key','claim_id','citekey','relation','rationale','reading_status','evidence_status','evidence_currentness','evidence')}
            claim_sources.setdefault(row['claim_id'],[]).append(relation)
            source_claims.setdefault(row['key'],[]).append(relation)
    attached_keys={row.get('citekey') for row in all_rows if row.get('citekey')}
    return {"project":project,"uses":uses,"claim_sources":claim_sources,"source_claims":source_claims,
            "unassociated_uses":[span for span in spans if span['citekey'] not in attached_keys],
            "source_revision":source.get('revision'),"diagnostics":traversal.get('diagnostics',[]),
            "citation_scope":{"kind":"query" if citation_keys is not None else "project",
                "key":requested_key or None,"normalized_key":key or None,"claim_id":claim_id or None,
                "citekeys":sorted(citation_keys) if citation_keys is not None else None,
                "attribution":"Matches authored source bindings/citekeys; paragraph entailment is not assessed."},
            "pagination":{"offset":offset,"limit":limit,"total":total,"next_offset":offset+len(rows) if total>offset+len(rows) else None,
                "citation_offset":citation_offset,"citation_limit":citation_limit,"citation_total":citation_total,
                "next_citation_offset":citation_offset+len(spans) if citation_total>citation_offset+len(spans) else None}}



@contextmanager
def _bibliography_source_scope(project, source, manuscript, root):
    """References retain their feature lock; source identity and bytes share a lease."""
    from laplace.manuscript import manuscript_source

    selected = (root / source["root"]).resolve() if source.get("root") else None
    if selected is None:
        yield
        return
    bib = _bib_path(manuscript, selected).resolve()
    expected = manuscript_source.selection_identity(source, project)
    with (
        manuscript_source.selection_mutation(project, root),
        manuscript_source.source_mutation([selected, bib]),
    ):
        current = manuscript_source.resolve(project, repo_root=root)
        current_root = (root / current["root"]).resolve() if current.get("root") else None
        if (
            manuscript_source.selection_identity(current, project) != expected
            or current_root != selected
            or _bib_path(manuscript, current_root).resolve() != bib
        ):
            raise ValueError(
                "Selected bibliography changed before reference source publication; inspect the current document."
            )
        yield


def _reference_source_effect(
    project, root, source, bib, before, intended, *, required="COMPLETE", reason=None
):
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import source_effects

    step = {"owner": "reference-association", "status": required}
    if reason:
        step["reason"] = reason
    effect = source_effects.receipt(
        project,
        manuscript_source.selection_identity(source, project),
        [source_effects.observed_file(root, bib, before, intended)],
        required=[step],
    )
    source_effects.finish(
        {}, project, root, effect, heading_sync={"status": "NOT_NEEDED", "updated": []}
    )
    if effect["impact"]["status"] != "NONE":
        effect["impact"]["reads"].append({"operation": "references_attached", "payload": {}})
    return effect


def _pending_association(provider,item,citekey,*,claim_id=None,canonical_id=None):
    row={'key':item['key'],'claim_id':claim_id,'citekey':citekey,'metadata':_metadata(item),
        'source':{'provider':provider,'revision':{'version':item.get('version',''),'modified':item.get('modified','')},'identity':_digest(_metadata(item))},
        'state':'CURRENT','reading_status':'unread','evidence_status':'metadata-only','bibliography_state':'PENDING'}
    if canonical_id:row['canonical_id']=canonical_id
    return row


def _attach_locked(project: str, payload: dict, root: Path | None = None, library: Library | None = None, imported: dict | None = None) -> tuple[int, dict]:
    root = (root or _root()).resolve(); library = library or Library()
    key = payload.get("key")
    if not isinstance(key, str) or not key: return 422, {"error": "reference key is required"}
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        return 403, {"error": "source is read-only; attaching a BibTeX entry would modify the imported original"}
    manuscript = _manuscript(project, root)
    if manuscript is None or not manuscript.is_dir(): return 404, {"error": "unknown project manuscript"}
    from laplace.research import literature
    provider, item = (imported["provider"], imported["item"]) if imported else literature.resolve_item(project, key, root, library)
    if item is None: return 404, {"error": "reference not found"}
    key = str(item.get("key") or key)
    citekey = payload.get("citekey") or item.get("citation_key") or literature.citekey(item)
    if not isinstance(citekey, str) or not _CITEKEY.fullmatch(citekey): return 422, {"error": "citekey is not BibTeX-safe"}
    rows = _load_associations(manuscript)
    before_rows=json.loads(json.dumps(rows));association_path=manuscript/_ASSOCIATIONS
    before_association=association_path.read_bytes() if association_path.is_file() else None
    if any(row.get("key") == key and row.get("claim_id") == payload.get("claim_id") for row in rows):
        return 409, {"error": "that item is already attached to that claim"}
    with _bibliography_source_scope(project, source, manuscript, root):
        selected_path=Path(source.get('root')) if source.get('root') else None
        if selected_path is not None and not selected_path.is_absolute(): selected_path=root/selected_path
        if selected_path is None or not _bibliography_names(selected_path):
            if any(row.get('citekey')==citekey and row.get('key')!=key for row in rows):return 409,{'error':'citekey collision: '+citekey}
            row=_pending_association(provider,item,citekey,claim_id=payload.get('claim_id'),canonical_id=payload.get('canonical_id'))
            _write_associations(manuscript,rows+[row])
            return 201,{'ok':True,'association':row,'owned_changes':_owned_associations(root,manuscript,before_association,before_rows,rows+[row],['references','research','pipeline']),'note':'Source saved before bibliography setup. Binding it for use will materialize its selected bibliography.'}
        bib = _bib_path(manuscript, selected_path).resolve()
        from laplace.pipeline import registry
        project_record = registry.resolve(project, repo_root=root)
        project_home = project_record.path(project_record.project_dir, root) if project_record and project_record.project_dir else manuscript
        shared_bib = project_record.path(project_record.bib, root) if project_record and project_record.bib else None
        if not bib.is_relative_to(project_home.resolve()) and not bib.is_relative_to(manuscript.resolve()) and (shared_bib is None or bib != shared_bib.resolve()):
            return 422, {"error":"The bibliography is outside the selected project and its registered shared bibliography."}
        before_bytes = bib.read_bytes() if bib.is_file() else None
        text = before_bytes.decode("utf-8") if before_bytes is not None else ""
        requested = next((entry for entry in _bib_entries(text) if entry['key'] == citekey), None)
        if requested and not _entry_matches(requested['text'], key, {str(item.get('doi') or '')}):
            return 409, {'error': f'citekey collision: {citekey}'}
        # Reuse a DOI or provider identity even when it already has a different key.
        identities = [entry for entry in _bib_entries(text) if _entry_matches(entry["text"], key, {str(item.get("doi") or "")})]
        if len(identities) > 1:
            return 409, {"error": "duplicate bibliography identity; consolidate existing entries", "citekeys": [e["key"] for e in identities]}
        if identities:
            citekey = identities[0]["key"]
        if citekey in set(_BIBKEY.findall(text)):
            # Reusing the same Zotero identity is safe and lets one source attach to
            # several claims; a different identity is a real citekey collision.
            entry_text = next(entry["text"] for entry in _bib_entries(text) if entry["key"] == citekey)
            if _entry_matches(entry_text, key, {str(item.get("doi") or "")}):
                pass
            else: return 409, {"error": f"citekey collision: {citekey}"}
        bib.parent.mkdir(parents=True, exist_ok=True)
        before_bib = text if bib.exists() else None
        if citekey not in set(_BIBKEY.findall(text)):
            addition = ("\n" if text and not text.endswith("\n") else "") + _bib_entry(item, citekey)
            pending = bib.with_name(bib.name + ".references.pending")
            pending.write_text(text + addition, encoding="utf-8")
            from laplace.manuscript.source_effects import publish
            publish(pending, bib)
        intended = (text + addition if citekey not in set(_BIBKEY.findall(text)) else text).encode("utf-8")
        row = {"key": key, "claim_id": payload.get("claim_id"), "note": payload.get("note", ""), "citekey": citekey,
               "bib_path": str(bib.relative_to(root)),
               "metadata": _metadata(item),
               "source": {"provider": provider, "revision": {"version": item.get("version", ""), "modified": item.get("modified", "")},
                          "identity": _digest({k: item.get(k) for k in ("key", "version", "modified", "title", "doi")})},
               "state": "CURRENT"}
        if payload.get("canonical_id"): row["canonical_id"] = payload["canonical_id"]
        row["reading_status"] = "unread"
        row["evidence_status"] = "metadata-only"
        try:
            _write_associations(manuscript, rows + [row])
        except BaseException as exc:
            from laplace.manuscript import source_effects
            cleanup_error = None
            try:
                if bib.read_bytes() == intended:
                    if before_bytes is None:
                        bib.unlink(missing_ok=True)
                    else:
                        source_effects.replace(bib, before_bytes)
            except OSError as cleanup:
                cleanup_error = str(cleanup)
            if not isinstance(exc, Exception):
                raise
            effect = _reference_source_effect(project, root, source, bib, before_bytes, intended,
                required='UNPROVED', reason=str(exc)+(('; source compensation: '+cleanup_error) if cleanup_error else ''))
            raise source_effects.SourceEffectFailure(exc, effect) from exc
        effect = _reference_source_effect(project, root, source, bib, before_bytes, intended)
        owned=_owned_associations(root,manuscript,before_association,before_rows,rows+[row],['references','research','manuscript','pipeline'])
        bib_after=text + addition if citekey not in set(_BIBKEY.findall(text)) else text
        if before_bib is None or bib_after!=before_bib:owned['files'].append(_owned_file(root,bib,before_bib.encode() if before_bib is not None else None,bib_after.encode()))
        return 201, {"ok": True, "association": row, "bib_path": bib.name, "owned_changes":owned, "source_effect":effect,
                     "note": "bibliographic metadata is attached; it is not entailment evidence for the claim"}


def _refresh_locked(project: str, root: Path | None = None, library: Library | None = None) -> tuple[int, dict]:
    root = (root or _root()).resolve(); library = library or Library(); manuscript = _manuscript(project, root)
    if manuscript is None or not manuscript.is_dir(): return 404, {"error": "unknown project manuscript"}
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'):
        return 403, {'error':'source is read-only'}
    rows = _load_associations(manuscript); before_rows=json.loads(json.dumps(rows)); changed = []
    before_association=(manuscript/_ASSOCIATIONS).read_bytes() if (manuscript/_ASSOCIATIONS).is_file() else None
    from laplace.research import literature
    rows=literature.canonical_associations(rows)
    cache = {}
    for row in rows:
        key = str(row.get("key") or "")
        if key not in cache:
            try:
                provider, item = literature.resolve_item(project, key, root, library, live=True)
                cache[key] = (provider, item, None)
            except (ValueError, OSError, TimeoutError) as exc:
                cache[key] = ((row.get('source') or {}).get('provider'), None, str(exc))
        provider, item, error = cache[key]
        if error:
            row['refresh'] = {'provider': provider, 'error': error, 'status': 'UNVERIFIED'}
            row['state'] = 'UNVERIFIED'
            continue
        old = ((row.get("source") or {}).get("revision"))
        now = {"version": item.get("version", ""), "modified": item.get("modified", "")} if item else None
        if now != old:
            row["state"] = "STALE"; row["refresh"] = {"provider": provider, "current_revision": now}; changed.append(row.get("key"))
        else:
            row['state'] = 'CURRENT'
            row.pop('refresh', None)
    _write_associations(manuscript, rows)
    return 200, {"ok": True, "owned_changes":_owned_associations(root,manuscript,before_association,before_rows,rows,["references","research","pipeline"]), "checked": len(rows), "stale": [key for key in changed if key],
                 "unverified": [row.get("key") for row in rows if row.get("state") == "UNVERIFIED"],
                 "note": "authored notes and citekeys are preserved; stale associations require review"}


def _update_locked(project: str, payload: dict, root: Path | None = None,
                   library: Library | None = None) -> tuple[int, dict]:
    root = (root or _root()).resolve(); library = library or Library()
    key = payload.get("key")
    if not isinstance(key, str) or not key:
        return 422, {"error": "reference key is required"}
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        return 403, {"error": "source is read-only"}
    manuscript = _manuscript(project, root)
    if manuscript is None or not manuscript.is_dir():
        return 404, {"error": "unknown project manuscript"}
    rows = _load_associations(manuscript)
    before_rows = json.loads(json.dumps(rows))
    before_association=(manuscript/_ASSOCIATIONS).read_bytes() if (manuscript/_ASSOCIATIONS).is_file() else None
    from laplace.research import literature
    provider, item = literature.resolve_item(project, key, root, library, live=True)
    if item is None:return 404,{"error":"reference not found"}
    key=str(item.get("key") or key)
    rows=literature.canonical_associations(rows,key=key)
    matched = [row for row in rows if row.get("key") == key]
    if not matched:
        return 404, {"error": "reference is not attached to this project"}
    if payload.get('metadata') is not None:
        if provider != 'local': return 422, {'error': 'Metadata edits are for local references; provider metadata is verified at its source.'}
        incoming = payload['metadata']
        if not isinstance(incoming, dict) or incoming.get('doi') or 'key' in incoming:
            return 422, {'error': 'Supply local metadata fields without changing its identity or assigning a DOI.'}
        item = {**item, **{k:v for k,v in _metadata(incoming).items() if k not in ('version','modified','provenance')}}
        if not str(item.get('title') or '').strip(): return 422, {'error': 'title must not be empty'}
        if not isinstance(item.get('creators', []), list) or not all(isinstance(x,str) for x in item.get('creators', [])):
            return 422, {'error': 'creators must be an array of names'}
        item['version'] = _digest({k:v for k,v in item.items() if k not in ('version','modified')})
    if item is None:
        return 404, {"error": "reference not found"}
    with _bibliography_source_scope(project, source, manuscript, root):
        selected = Path(source.get("root")) if source.get("root") else None
        if selected is not None and not selected.is_absolute(): selected = root / selected
        if selected is None or not selected.is_file() or not _bibliography_names(selected):
            return 422, {"error": "selected manuscript has no bibliography consumer"}
        bib = _bib_path(manuscript, selected).resolve()
        from laplace.pipeline import registry
        project_record = registry.resolve(project, repo_root=root)
        project_home = project_record.path(project_record.project_dir, root) if project_record and project_record.project_dir else manuscript
        shared_bib = project_record.path(project_record.bib, root) if project_record and project_record.bib else None
        if not bib.is_relative_to(project_home.resolve()) and not bib.is_relative_to(manuscript.resolve()) \
                and (shared_bib is None or bib != shared_bib.resolve()):
            return 422, {"error": "The bibliography is outside the selected project and its registered shared bibliography."}
        if not bib.is_file():
            return 409, {"error": "attached bibliography is missing"}
        bib_relative = str(bib.relative_to(root))
        foreign_bib = sorted({str(row.get("bib_path")) for row in matched
                              if row.get("bib_path") and str(row.get("bib_path")) != bib_relative})
        if foreign_bib:
            return 409, {"error": "attached reference belongs to a different selected bibliography",
                         "attached_bibliographies": foreign_bib, "selected_bibliography": bib_relative}
        before_bytes = bib.read_bytes()
        before_bib = before_bytes.decode("utf-8")
        entries = _bib_entries(before_bib)
        # The existing association proves the old entry's identity.  The incoming
        # DOI may itself be the changed metadata under review and cannot be used to
        # claim a previously unrelated entry.
        old_dois = {str((row.get("metadata") or {}).get("doi") or "") for row in matched}
        replacements: list[tuple[int, int, str, str]] = []
        for citekey in dict.fromkeys(str(row.get("citekey") or "") for row in matched):
            entry = next((candidate for candidate in entries if candidate["key"] == citekey), None)
            if entry is None:
                return 409, {"error": f"attached BibTeX entry is missing: {citekey}"}
            if not entry["closed"]:
                return 409, {"error": f"attached BibTeX entry is malformed: {citekey}"}
            if not _entry_matches(entry["text"], key, old_dois):
                return 409, {"error": f"attached BibTeX entry identity no longer matches: {citekey}"}
            replacements.append((entry["start"], entry["end"], _bib_entry(item, citekey), entry["text"]))
        after_bib = before_bib
        for start, end, replacement, _old in sorted(replacements, reverse=True):
            after_bib = after_bib[:start] + replacement + after_bib[end:]
        metadata = _metadata(item)
        revision = {"version": item.get("version", ""), "modified": item.get("modified", "")}
        identity = _digest({field: item.get(field) for field in ("key", "version", "modified", "title", "doi")})
        for row in rows:
            if row.get("key") != key:
                continue
            row["source"] = {"provider": provider, "revision": revision, "identity": identity}
            row["bib_path"] = bib_relative
            row["metadata"] = metadata
            row["state"] = "CURRENT"
            row.pop("refresh", None)
        association_text = json.dumps({"schema_version": "laplace.references/1", "associations": rows},
                                      indent=2, sort_keys=True) + "\n"
        from laplace.core.records import journal
        (root / "contract").mkdir(parents=True, exist_ok=True)
        journal.bank_row("contract/talk.jsonl", {
            "record": "reference-update", "id": "REFUP-" + hashlib.sha256(
                (project + key + identity).encode()).hexdigest()[:20],
            "project": project, "key": key, "bib_path": str(bib.relative_to(root)),
            "before": {"entries": [old for _start, _end, _new, old in replacements],
                       "associations": [row for row in before_rows if row.get("key") == key]},
            "after": {"entries": [new for _start, _end, new, _old in replacements],
                      "associations": [row for row in rows if row.get("key") == key]},
        }, root=root)
        bib_pending = bib.with_name(bib.name + ".update.pending")
        assoc = manuscript / _ASSOCIATIONS
        assoc_pending = assoc.with_name(assoc.name + ".update.pending")
        bib_pending.write_text(after_bib, encoding="utf-8")
        assoc_pending.write_text(association_text, encoding="utf-8")
        from laplace.manuscript import source_effects
        source_effects.publish(bib_pending, bib)
        try:
            assoc_pending.replace(assoc)
        except BaseException as exc:
            cleanup_error = None
            try:
                if bib.read_bytes() == after_bib.encode('utf-8'):
                    source_effects.replace(bib, before_bytes)
            except OSError as cleanup:
                cleanup_error = str(cleanup)
            finally:
                try:
                    assoc_pending.unlink(missing_ok=True)
                except OSError as cleanup:
                    cleanup_error = (cleanup_error + '; ' if cleanup_error else '') + str(cleanup)
            if not isinstance(exc, Exception):
                raise
            effect = _reference_source_effect(project, root, source, bib, before_bytes, after_bib.encode('utf-8'),
                required='UNPROVED', reason=str(exc)+(('; source compensation: '+cleanup_error) if cleanup_error else ''))
            raise source_effects.SourceEffectFailure(exc, effect) from exc
        effect = _reference_source_effect(project, root, source, bib, before_bytes, after_bib.encode('utf-8'))
        owned=_owned_associations(root,manuscript,before_association,before_rows,rows,['references','research','manuscript','pipeline'])
        if before_bib!=after_bib:owned['files'].append(_owned_file(root,bib,before_bib.encode(),after_bib.encode()))
        return 200, {"ok": True, "key": key, "updated": len(matched), "owned_changes":owned, "source_effect":effect,
                     "citekeys": list(dict.fromkeys(row["citekey"] for row in matched)),
                     "revision": revision, "state": "CURRENT"}

def bibliography_entry(project: str, citekey: str, root: Path) -> dict:
    """Current selected bibliography metadata; this is not external source text."""
    from laplace.manuscript import manuscript_source
    if not _CITEKEY.fullmatch(citekey):
        raise ValueError('A bibliography read requires an exact citation key.')
    source = manuscript_source.resolve(project, root, include_candidates=False)
    main = (root / source['root']) if source.get('root') else None
    entries = []
    if main:
        for name in _bibliography_names(main):
            path = (main.parent / (name if name.endswith('.bib') else name + '.bib')).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            raw = path.read_bytes()
            for row in _bib_entries(raw.decode('utf-8')):
                if row['key'] != citekey:
                    continue
                rel = path.relative_to(root).as_posix()
                complete = len(row['text'].encode('utf-8')) <= 40000
                entries.append({'file': rel, 'citekey': citekey,
                    'content': row['text'] if complete else None, 'complete': complete,
                    'revision': 'sha256:' + hashlib.sha256(row['text'].encode()).hexdigest(),
                    'file_revision': 'sha256:' + hashlib.sha256(raw).hexdigest(),
                    'source_read': {'http': {'method':'GET','route':'/projection/tex',
                        'query': {'corpus':project,'file':rel,'view':'source'}}}})
    return {'project': project, 'citekey': citekey,
        'status': 'AVAILABLE' if len(entries)==1 else 'AMBIGUOUS' if entries else 'MISSING',
        'entries': entries, 'meaning': 'Bibliography entry metadata, not evidence that the cited source was read.',
        'read_handle': {'operation':'references_attached','payload':{'citekey':citekey},
            'http': {'method':'GET','route':'/references/attached','query':{'project':project,'citekey':citekey}}}}


def attached(project:str,root:Path|None=None,library:Library|None=None,*,citekey:str="")->dict|None:
    root=(root or _root()).resolve(); manuscript=_manuscript(project,root)
    if manuscript is None:return None
    if citekey:
        return bibliography_entry(project, citekey, root)
    library=library or Library(); rows=[]
    for row in _load_associations(manuscript):
        provider = (row.get('source') or {}).get('provider', 'unknown')
        rows.append({**row, 'provider': provider})
    return {'project':project,'associations':rows}

def attach(project: str, payload: dict, root: Path | None=None, library: Library | None=None):
    from filelock import FileLock
    root=(root or _root()).resolve(); manuscript=_manuscript(project,root)
    if manuscript is None or not manuscript.is_dir(): return 404, {"error":"unknown project manuscript"}
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'): return 403, {"error":"source is read-only"}
    with FileLock(str(manuscript/'.references.lock'), timeout=15):
        return _attach_locked(project,payload,root,library)


def refresh(project: str, root: Path | None=None, library: Library | None=None):
    from filelock import FileLock
    root=(root or _root()).resolve(); manuscript=_manuscript(project,root)
    if manuscript is None or not manuscript.is_dir(): return 404, {"error":"unknown project manuscript"}
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'): return 403, {"error":"source is read-only"}
    with FileLock(str(manuscript/'.references.lock'), timeout=15):
        return _refresh_locked(project,root,library)


def update(project: str, payload: dict, root: Path | None=None, library: Library | None=None):
    from filelock import FileLock
    root=(root or _root()).resolve(); manuscript=_manuscript(project,root)
    if manuscript is None or not manuscript.is_dir(): return 404, {"error":"unknown project manuscript"}
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'): return 403, {"error":"source is read-only"}
    with FileLock(str(manuscript/'.references.lock'), timeout=15):
        return _update_locked(project,payload,root,library)


def handle(path: str, query: dict, method: str, body: bytes, repo_root=None) -> tuple[int, str, bytes] | None:
    if path != "/references" and not path.startswith("/references/"): return None
    method = (method or "GET").upper(); library = Library(); project = _q1(query,"project")
    from laplace.research import literature
    result = literature.handle(path, query, method, body, repo_root)
    if result is not None: return result
    if path == "/references/status":
        return _response(200, library.status()) if method == "GET" else _response(405, {"error": "GET only"})
    if path == "/references/search":
        q = _q1(query, "q")
        if method != "GET": return _response(405, {"error": "GET only"})
        if not q: return _response(422, {"error": "q= is required"})
        provider, items = library.search(q)
        return _response(200, {"provider": provider, "q": q, "items": items, "limit": 30})
    if path == "/references/literature-discover" and method == "GET":
        q=_q1(query,"q")
        if not q:return _response(422,{"error":"q= is required"})
        try:return _response(200,literature_discover(q,int(_q1(query,"limit") or 10),root=repo_root))
        except (ValueError,urllib.error.URLError,OSError) as exc:return _response(502,{"error":str(exc),"provider":"crossref"})
    if path == "/references/literature-uses" and method == "GET":
        try:
            return _response(200,literature_uses(project,root=repo_root,key=_q1(query,"key"),claim_id=_q1(query,"claim_id"),offset=int(_q1(query,"offset") or 0),limit=int(_q1(query,"limit") or 100),citation_offset=int(_q1(query,"citation_offset") or 0),citation_limit=int(_q1(query,"citation_limit") or 200)))
        except ValueError as exc: return _response(422, {'error': str(exc)})
    if path == "/references/item":
        key = _q1(query, "key")
        if method != "GET": return _response(405, {"error": "GET only"})
        if not _KEY.fullmatch(key): return _response(422, {"error": "eight-character key required"})
        provider, item = library.item(key)
        return _response(200, {"provider": provider, "item": item}) if item else _response(404, {"error": "item not found"})
    if path == "/references/text":
        key = _q1(query, "key")
        if method != "GET" or not _KEY.fullmatch(key): return _response(422, {"error": "eight-character key required"})
        try: return _response(200, extract_text(key, library, limit=int(_q1(query,"limit") or 24000), offset=int(_q1(query,"offset") or 0)))
        except ValueError as exc: return _response(404, {"error": str(exc)})
    if path == '/references/attached':
        try:
            out=attached(project,root=repo_root,library=library,citekey=_q1(query,"citekey"))
        except ValueError as exc:
            return _response(422,{"error":str(exc)})
        return _response(200,out) if out else _response(404,{'error':'project not found'})
    if path in {"/references/attach", "/references/refresh", "/references/update"}:
        if method != "POST": return _response(405, {"error": "POST only"})
        try: payload = json.loads(body or b"{}")
        except (TypeError, ValueError): return _response(400, {"error": "bad json"})
        if not isinstance(payload, dict): return _response(400, {"error": "body must be an object"})
        project = _q1(query, "project") or payload.get("project", "")
        try:
            status, out = (attach(project, payload, root=repo_root) if path.endswith("attach") else
                           update(project, payload, root=repo_root) if path.endswith("update") else
                           refresh(project, root=repo_root))
            return _response(status, out)
        except urllib.error.HTTPError as exc:
            return _response(404 if exc.code == 404 else 502, {'error': str(exc), 'retryable': exc.code != 404})
        except (urllib.error.URLError, TimeoutError) as exc:
            return _response(502, {'error': str(exc), 'retryable': True})
        except (ValueError, OSError) as exc:
            from laplace.manuscript.source_effects import error_details
            details = error_details(exc)
            return _response(409, {'error':str(exc), **details, 'retryable':not bool(details)})
    return _response(404, {"error": "unknown references route"})

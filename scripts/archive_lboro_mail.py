#!/usr/bin/env python3
"""archive_lboro_mail.py — custody sifter for the Loughborough mailbox.

His scope, verbatim: "restrict it to chains in which I've sent an email."

So the unit of custody is the THREAD, not the message: a thread is kept in full
(every message in it, including the ones he only received) iff at least one of
its messages was SENT BY HIM. Threads he never spoke in are dropped.

READ-ONLY against the Thunderbird profile and against the server. This script
never contacts IMAP, never writes into the profile, and never deletes anything.
It reads Thunderbird's on-disk mbox stores (storeContractID = berkeleystore) and
writes a separate archive tree.

Thunderbird's IMAP store, per folder, is TWO files:
  <Folder>       — the mbox: the actual downloaded messages (absent = nothing local)
  <Folder>.msf   — the summary/index: headers and flags only, a Mork database
A .msf with no mbox beside it means the folder is known but NOT downloaded. This
script reports that state honestly rather than silently archiving nothing.

Usage:
    python3 scripts/archive_lboro_mail.py                     # default profile, default out
    python3 scripts/archive_lboro_mail.py --profile PATH --out DIR
    python3 scripts/archive_lboro_mail.py --me a@b.ac.uk --me c@d.com
    python3 scripts/archive_lboro_mail.py --assess-only       # sync-state report, no writes

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mailbox
import os
import re
import sys
from collections import Counter, defaultdict
from email.utils import getaddresses, parsedate_to_datetime

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

DEFAULT_PROFILE = os.path.expanduser("~/.thunderbird/p7v77pgm.default-esr")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO_ROOT, "archive", "loughborough_mail")

# Files inside a Thunderbird store dir that are never mbox message stores.
NON_MBOX_SUFFIXES = (".msf", ".dat", ".sqlite", ".json", ".html", ".log", ".bak")

# Subject-fallback threading is a LAST RESORT and over-merges on generic subjects.
# These normalized subjects never union by subject alone.
GENERIC_SUBJECTS = {
    "", "hi", "hello", "hey", "thanks", "thank you", "ta", "cheers", "ok", "okay",
    "meeting", "question", "questions", "update", "updates", "test", "testing",
    "follow up", "followup", "fyi", "reminder", "notes", "note", "call", "info",
    "information", "request", "hello!", "quick question", "catch up", "chat",
    "paper", "papers", "draft", "drafts", "reference", "references", "help",
    "no subject", "(no subject)", "read receipt", "out of office", "automatic reply",
}
# ...and neither does anything shorter than this once Re:/Fwd: are stripped.
MIN_SUBJECT_LEN = 8
# Two same-subject messages only join if they are within this many days of each
# other in the sorted-by-date chain. Stops a decade of "Seminar announcement"
# collapsing into one thread.
SUBJECT_WINDOW_DAYS = 365

RE_PREFIX = re.compile(
    r"^\s*(?:(?:re|aw|sv|vs|rv|tr|fw|fwd|antw|odp|ynt|res|enc)\s*(?:\[\d+\])?\s*:\s*)+",
    re.IGNORECASE,
)
RE_WS = re.compile(r"\s+")
# Thunderbird's high status bits live in X-Mozilla-Status2; 0x10000 == Partial,
# i.e. headers pulled but the body never downloaded.
MOZ_PARTIAL = 0x10000


# ---------------------------------------------------------------------------
# profile inspection
# ---------------------------------------------------------------------------


def read_prefs(profile: str) -> dict:
    """Parse user_pref() lines out of prefs.js. Read-only."""
    path = os.path.join(profile, "prefs.js")
    prefs: dict = {}
    if not os.path.exists(path):
        return prefs
    pat = re.compile(r'^user_pref\("([^"]+)",\s*(.*)\);\s*$')
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pat.match(line.strip())
            if not m:
                continue
            key, raw = m.group(1), m.group(2).strip()
            if raw.startswith('"') and raw.endswith('"'):
                val = raw[1:-1]
            elif raw in ("true", "false"):
                val = raw == "true"
            else:
                try:
                    val = int(raw)
                except ValueError:
                    val = raw
            prefs[key] = val
    return prefs


def identity_addresses(prefs: dict) -> list[str]:
    """Every mail.identity.*.useremail in the profile, lowercased."""
    out = []
    for k, v in prefs.items():
        if k.startswith("mail.identity.") and k.endswith(".useremail") and isinstance(v, str):
            if v.strip():
                out.append(v.strip().lower())
    return sorted(set(out))


def identity_names(prefs: dict) -> list[str]:
    out = []
    for k, v in prefs.items():
        if k.startswith("mail.identity.") and k.endswith(".fullName") and isinstance(v, str):
            if v.strip():
                out.append(v.strip())
    return sorted(set(out))


AUTH_METHODS = {
    0: "undefined", 1: "none", 3: "password-cleartext", 4: "password-encrypted",
    5: "GSSAPI", 6: "NTLM", 7: "TLS-client-cert", 10: "OAuth2",
}


def server_report(prefs: dict) -> list[dict]:
    """One row per mail.server.serverN of type imap/pop3."""
    ids = sorted({k.split(".")[2] for k in prefs if k.startswith("mail.server.server")})
    rows = []
    for sid in ids:
        p = f"mail.server.{sid}."
        stype = prefs.get(p + "type")
        if stype not in ("imap", "pop3"):
            continue
        auth = prefs.get(p + "authMethod")
        rows.append({
            "server_id": sid,
            "type": stype,
            "hostname": prefs.get(p + "hostname"),
            "username": prefs.get(p + "userName"),
            "port": prefs.get(p + "port"),
            "auth_method_code": auth,
            "auth_method": AUTH_METHODS.get(auth, f"unknown({auth})"),
            "store": prefs.get(p + "storeContractID"),
            "directory": prefs.get(p + "directory"),
            # absent pref => Thunderbird default; recorded as None, not guessed
            "offline_download_pref": prefs.get(p + "offline_download"),
        })
    return rows


def folder_cache(profile: str) -> dict:
    path = os.path.join(profile, "folderCache.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except Exception:
        return {}


def scan_stores(profile: str) -> list[dict]:
    """Every mail store dir under the profile; per folder, mbox present or .msf-only.

    Walks ImapMail/ and Mail/ including .sbd subfolder dirs.
    """
    cache = folder_cache(profile)
    folders: dict[str, dict] = {}

    roots = [os.path.join(profile, "ImapMail"), os.path.join(profile, "Mail")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                if fn.endswith(".msf"):
                    base = full[: -len(".msf")]
                    rec = folders.setdefault(base, {})
                    rec["msf_path"] = full
                    rec["msf_bytes"] = os.path.getsize(full)
                elif not fn.endswith(NON_MBOX_SUFFIXES) and not fn.startswith("."):
                    rec = folders.setdefault(full, {})
                    rec["mbox_path"] = full
                    rec["mbox_bytes"] = os.path.getsize(full)

    rows = []
    for base, rec in sorted(folders.items()):
        rel = os.path.relpath(base, profile)
        # a .msf entry can point at the account-level summary (…/server.msf); it has
        # no folder of its own, but reporting it is honest.
        cinfo = cache.get(rec.get("msf_path", "")) or cache.get(base) or {}
        rows.append({
            "label": rel,
            "base_path": base,
            "mbox_path": rec.get("mbox_path"),
            "mbox_bytes": rec.get("mbox_bytes", 0),
            "msf_path": rec.get("msf_path"),
            "msf_bytes": rec.get("msf_bytes", 0),
            "online_name": cinfo.get("onlineName"),
            "server_total": cinfo.get("serverTotal"),
            "summary_total_msgs": cinfo.get("totalMsgs"),
            "cached_folder_size": cinfo.get("folderSize"),
            "state": _folder_state(rec, cinfo),
        })
    return rows


def _folder_state(rec: dict, cinfo: dict) -> str:
    mb = rec.get("mbox_bytes", 0)
    if rec.get("mbox_path") and mb > 0:
        return "DOWNLOADED"
    if rec.get("mbox_path"):
        return "EMPTY_MBOX"
    if rec.get("msf_path"):
        st = cinfo.get("serverTotal")
        if isinstance(st, int) and st > 0:
            return "SUMMARY_ONLY (server has %d msgs, none downloaded)" % st
        return "SUMMARY_ONLY (not synced)"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# message model
# ---------------------------------------------------------------------------


class Msg:
    __slots__ = (
        "folder", "key", "msgid", "refs", "subject", "norm_subject", "from_addrs",
        "from_raw", "participants", "date", "date_raw", "is_mine", "partial",
        "size", "node",
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def norm_subject(s: str | None) -> str:
    if not s:
        return ""
    s = RE_PREFIX.sub("", s)
    s = RE_WS.sub(" ", s).strip().lower()
    return s


def header_addrs(msg, *names) -> list[str]:
    vals = []
    for n in names:
        vals.extend(msg.get_all(n, []))
    out = []
    for _disp, addr in getaddresses([str(v) for v in vals]):
        a = (addr or "").strip().lower()
        if a and "@" in a:
            out.append(a)
    return out


def parse_msgids(raw) -> list[str]:
    if not raw:
        return []
    return re.findall(r"<[^<>@\s]+@[^<>\s]+>", str(raw))


def msg_date(msg):
    raw = msg.get("Date")
    if not raw:
        return None, None
    try:
        d = parsedate_to_datetime(str(raw))
        if d is None:
            return None, str(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d, str(raw)
    except Exception:
        return None, str(raw)


def moz_partial(msg) -> bool:
    v = msg.get("X-Mozilla-Status2")
    if not v:
        return False
    try:
        return bool(int(str(v).strip(), 16) & MOZ_PARTIAL)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# union-find over thread nodes
# ---------------------------------------------------------------------------


class DSU:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# ---------------------------------------------------------------------------
# the sift
# ---------------------------------------------------------------------------


def load_folder(row: dict, me: set[str], errors: list[str]) -> tuple[list[Msg], object]:
    """Parse one folder's mbox into Msg records. Returns (msgs, open_mbox)."""
    path = row["mbox_path"]
    box = mailbox.mbox(path, create=False)
    msgs: list[Msg] = []
    for key in box.keys():
        try:
            m = box[key]
        except Exception as exc:  # a corrupt entry must not kill the archive run
            errors.append(f"{row['label']}[{key}]: parse failed: {exc!r}")
            continue
        mid_list = parse_msgids(m.get("Message-ID") or m.get("Message-Id"))
        msgid = mid_list[0] if mid_list else None
        refs = parse_msgids(m.get("References")) + parse_msgids(m.get("In-Reply-To"))
        subj = m.get("Subject")
        subj = str(subj) if subj is not None else ""
        frm = header_addrs(m, "From")
        d, d_raw = msg_date(m)
        try:
            size = len(box.get_bytes(key))
        except Exception:
            size = 0
        node = msgid or "x-nomsgid:%s:%s" % (row["label"], key)
        msgs.append(Msg(
            folder=row["label"], key=key, msgid=msgid, refs=refs,
            subject=subj, norm_subject=norm_subject(subj),
            from_addrs=frm, from_raw=str(m.get("From") or ""),
            participants=sorted(set(frm + header_addrs(m, "To", "Cc"))),
            date=d, date_raw=d_raw,
            is_mine=any(a in me for a in frm),
            partial=moz_partial(m), size=size, node=node,
        ))
    return msgs, box


def build_threads(msgs: list[Msg]) -> dict[str, list[Msg]]:
    dsu = DSU()
    for m in msgs:
        dsu.find(m.node)
        for r in m.refs:
            dsu.union(m.node, r)

    # subject fallback: only for non-generic subjects, only between messages
    # adjacent in time within the window, and only when neither already shares a
    # Message-ID-derived thread (the union is harmless if they do).
    by_subj: dict[str, list[Msg]] = defaultdict(list)
    for m in msgs:
        s = m.norm_subject
        if len(s) >= MIN_SUBJECT_LEN and s not in GENERIC_SUBJECTS:
            by_subj[s].append(m)
    far = dt.timedelta(days=SUBJECT_WINDOW_DAYS)
    for s, group in by_subj.items():
        if len(group) < 2:
            continue
        dated = sorted([m for m in group if m.date], key=lambda m: m.date)
        undated = [m for m in group if not m.date]
        for a, b in zip(dated, dated[1:]):
            if b.date - a.date <= far:
                dsu.union(a.node, b.node)
        # undated messages join the group's first dated member (best available)
        anchor = dated[0] if dated else (undated[0] if undated else None)
        for m in undated:
            if anchor is not None:
                dsu.union(anchor.node, m.node)

    threads: dict[str, list[Msg]] = defaultdict(list)
    for m in msgs:
        threads[dsu.find(m.node)].append(m)
    return threads


def thread_id(members: list[Msg]) -> str:
    ids = sorted({m.msgid for m in members if m.msgid})
    if not ids:
        ids = sorted({m.node for m in members})
    h = hashlib.sha1("\n".join(ids).encode("utf-8", "replace")).hexdigest()
    return "th-" + h[:16]


def best_subject(members: list[Msg]) -> str:
    dated = sorted(members, key=lambda m: (m.date is None, m.date or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
    for m in dated:
        if m.subject.strip():
            return RE_PREFIX.sub("", m.subject).strip() or m.subject.strip()
    return ""


def run(args) -> int:
    profile = os.path.abspath(os.path.expanduser(args.profile))
    prefs = read_prefs(profile)
    ids = identity_addresses(prefs)
    me = {a.lower() for a in ids} | {a.strip().lower() for a in (args.me or []) if a.strip()}
    servers = server_report(prefs)
    folders = scan_stores(profile)

    # ---- assessment (always printed; it is the honest half of the job) ----
    print("=" * 78)
    print("PROFILE: %s" % profile)
    print("IDENTITIES (mail.identity.*.useremail): %s" % (", ".join(ids) or "NONE FOUND"))
    if args.me:
        print("EXTRA --me ADDRESSES: %s" % ", ".join(args.me))
    for n in identity_names(prefs):
        print("IDENTITY NAME: %s" % n)
    for s in servers:
        print("SERVER %s: %s://%s:%s user=%s auth=%s store=%s" % (
            s["server_id"], s["type"], s["hostname"], s["port"], s["username"],
            s["auth_method"], (s["store"] or "").split("/")[-1]))
    print("-" * 78)
    print("%-46s %-10s %10s  %s" % ("FOLDER", "MBOX", "MSF B", "STATE"))
    total_mbox_bytes = 0
    for f in folders:
        total_mbox_bytes += f["mbox_bytes"]
        print("%-46s %-10s %10d  %s" % (
            f["label"][:46],
            ("%d B" % f["mbox_bytes"]) if f["mbox_path"] else "ABSENT",
            f["msf_bytes"], f["state"]))
    downloaded = [f for f in folders if f["mbox_path"] and f["mbox_bytes"] > 0]
    print("-" * 78)
    print("folders known: %d | with a non-empty mbox: %d | local mbox bytes: %d"
          % (len(folders), len(downloaded), total_mbox_bytes))
    server_known = sum(f["server_total"] for f in folders if isinstance(f.get("server_total"), int) and f["server_total"] > 0)
    if server_known:
        print("server-side message count known to the summary files: %d" % server_known)
    print("=" * 78)

    if not me:
        print("FATAL: no identity address found and none supplied with --me.", file=sys.stderr)
        return 2

    if args.assess_only:
        return 0

    if not downloaded:
        print("\nNOTHING TO SIFT: no folder has a non-empty mbox on disk.")
        print("The messages are on the server only. See the report above for which")
        print("folders exist; nothing was written. Re-run after a download.")
        # still emit a summary so the run leaves a record
        _write_summary(args, profile, ids, list(me), servers, folders, [], {}, 0, 0, [], Counter())
        return 0

    # ---- parse ----
    errors: list[str] = []
    all_msgs: list[Msg] = []
    boxes: dict[str, object] = {}
    for f in downloaded:
        msgs, box = load_folder(f, me, errors)
        boxes[f["label"]] = box
        all_msgs.extend(msgs)
        print("parsed %-40s %6d messages" % (f["label"], len(msgs)))

    from_counter = Counter()
    for m in all_msgs:
        for a in m.from_addrs:
            from_counter[a] += 1

    threads = build_threads(all_msgs)
    kept, dropped = {}, 0
    for tid_key, members in threads.items():
        if any(m.is_mine for m in members):
            kept[tid_key] = members
        else:
            dropped += 1

    # ---- write ----
    outdir = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(outdir, exist_ok=True)
    keep_keys: dict[str, set] = defaultdict(set)
    for members in kept.values():
        for m in members:
            keep_keys[m.folder].add(m.key)

    written_bytes = 0
    written_msgs = 0
    per_folder = []
    for f in downloaded:
        label = f["label"]
        keys = keep_keys.get(label, set())
        if not keys:
            per_folder.append({"folder": label, "messages_written": 0, "bytes_written": 0})
            continue
        safe = label.replace(os.sep, "__").replace(" ", "_")
        target = os.path.join(outdir, safe + ".mbox")
        box = boxes[label]
        n = 0
        with open(target, "wb") as out:
            for key in box.keys():
                if key not in keys:
                    continue
                try:
                    raw = box.get_bytes(key)
                    frm = box[key].get_from() or "archive@localhost"
                except Exception as exc:
                    errors.append(f"{label}[{key}]: copy failed: {exc!r}")
                    continue
                out.write(b"From " + str(frm).encode("utf-8", "replace") + b"\n")
                out.write(raw)
                if not raw.endswith(b"\n"):
                    out.write(b"\n")
                out.write(b"\n")
                n += 1
        b = os.path.getsize(target)
        written_bytes += b
        written_msgs += n
        per_folder.append({"folder": label, "output": target, "messages_written": n, "bytes_written": b})
        print("wrote  %-40s %6d messages  %10d B" % (os.path.basename(target), n, b))

    for box in boxes.values():
        try:
            box.close()
        except Exception:
            pass

    # ---- manifest ----
    manifest = os.path.join(outdir, "threads.jsonl")
    with open(manifest, "w", encoding="utf-8") as fh:
        for members in sorted(kept.values(), key=lambda ms: min(
                [m.date for m in ms if m.date] or [dt.datetime.max.replace(tzinfo=dt.timezone.utc)])):
            dates = sorted(m.date for m in members if m.date)
            parts = sorted({a for m in members for a in m.participants})
            row = {
                "thread_id": thread_id(members),
                "subject": best_subject(members),
                "participants": parts,
                "date_first": dates[0].isoformat() if dates else None,
                "date_last": dates[-1].isoformat() if dates else None,
                "message_count": len(members),
                "my_message_count": sum(1 for m in members if m.is_mine),
                "folders": sorted({m.folder for m in members}),
                "message_ids": sorted({m.msgid for m in members if m.msgid}),
                "undated_messages": sum(1 for m in members if not m.date),
                "partial_messages": sum(1 for m in members if m.partial),
                "bytes": sum(m.size for m in members),
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("-" * 78)
    print("threads total %d | KEPT %d | dropped (no message from him) %d"
          % (len(threads), len(kept), dropped))
    print("messages parsed %d | archived %d | bytes archived %d"
          % (len(all_msgs), written_msgs, written_bytes))
    print("partial (headers-only, body never downloaded) messages: %d"
          % sum(1 for m in all_msgs if m.partial))
    if errors:
        print("ERRORS (%d) — first 10:" % len(errors))
        for e in errors[:10]:
            print("  " + e)

    # Alias surfacing: never guessed at, only reported for his ruling. Matched on
    # NAME tokens, not on the domain — every colleague is @lboro.ac.uk, so a domain
    # match would bury the signal (measured on the fixture: dept@lboro.ac.uk surfaced).
    name_tokens = set()
    for n in identity_names(prefs):
        for tok in re.split(r"[^A-Za-z]+", n):
            if len(tok) >= 4:
                name_tokens.add(tok.lower())
    for a in me:
        local = a.split("@")[0]
        for tok in re.split(r"[^A-Za-z]+", local):
            if len(tok) >= 4:
                name_tokens.add(tok.lower())
    cand = [(a, c) for a, c in from_counter.items()
            if a not in me and any(t in a.split("@")[0].lower() for t in name_tokens)]
    if cand:
        print("\nPOSSIBLE FURTHER ADDRESSES OF HIS seen in From: (NOT counted as his —")
        print("re-run with --me <addr> if any of these are also him):")
        for a, c in sorted(cand, key=lambda t: -t[1])[:20]:
            print("   %-45s %5d messages" % (a, c))

    _write_summary(args, profile, ids, sorted(me), servers, folders, per_folder,
                   {"threads_total": len(threads), "threads_kept": len(kept),
                    "threads_dropped": dropped},
                   written_msgs, written_bytes, errors, from_counter)
    print("\nmanifest: %s" % manifest)
    print("outdir:   %s" % outdir)
    return 0


def _write_summary(args, profile, ids, me, servers, folders, per_folder, thread_stats,
                   written_msgs, written_bytes, errors, from_counter):
    outdir = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "run_summary.json")
    payload = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "threads containing at least one message sent by him",
        "profile": profile,
        "identity_addresses": ids,
        "matched_as_his": me,
        "servers": servers,
        "folders": folders,
        "per_folder_output": per_folder,
        "threads": thread_stats,
        "messages_archived": written_msgs,
        "bytes_archived": written_bytes,
        "errors": errors[:200],
        "top_from_addresses": from_counter.most_common(40),
        "read_only": True,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("summary:  %s" % path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="Thunderbird profile dir (default: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="archive output dir (default: %(default)s)")
    ap.add_argument("--me", action="append", default=[],
                    help="extra address to treat as his; repeatable")
    ap.add_argument("--assess-only", action="store_true",
                    help="print the sync-state report and exit without writing")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())

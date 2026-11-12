from pathlib import Path
from walk_source import walk_declarations, walk_source

from laplace.manuscript import walk


def test_literal_tex_owner_urls_decode_escaped_delimiters_but_never_macros_or_policy():
    material=r'/projects/material-references?project=book\&path=chapters\%2Fchapter\_08.tex'
    work=r'/work/state?project=book\&view=detail\&id=WORK-source'
    for command,value,expected in [('href',material,'/projects/material-references?project=book&path=chapters%2Fchapter_08.tex'),
                                   ('url',work,'/work/state?project=book&view=detail&id=WORK-source')]:
        text='\\'+command+'{'+value+'}'+('{Read owner}' if command=='href' else '')
        row=walk.tex_pieces(text,{})[0]
        assert row['url']==expected and row['url_source']==value
        assert row['o_start']==0 and row['o_end']==len(text)
    unresolved=r'\href{/work\state?project=book\&id=\unknown}{Source}'
    row=walk.tex_pieces(unresolved,{})[0]
    assert row['url'] is None and row['url_source']==r'/work\state?project=book\&id=\unknown'
    unsafe=walk.tex_pieces(r'\href{javascript:alert(1)}{Unsafe}',{})[0]
    assert unsafe['url']=='javascript:alert(1)'  # Existing URI policy must still refuse it.


def test_table_and_theorem_blocks_are_typed_and_keep_source_span():
    text = "\\begin{theorem}\nA statement.\n\\end{theorem}\n\\begin{tabular}{cc}\na & b \\\\ \n\\end{tabular}\n"
    blocks = walk.blocks_for(text, file_rel="S.tex", repo_file="S.tex", md=__import__('pathlib').Path('.'),
                             corpus="", dir_param="", para_spans=[], known_macros=frozenset())
    assert [block["kind"] for block in blocks] == ["theorem", "table"]
    assert [[cell["tex"] for cell in row["cells"]] for row in blocks[1]["rows"]] == [["a", "b"]]
    assert blocks[0]["src"]["line_start"] == 1

def test_hierarchy_and_optional_theorem_name_remain_typed():
    text = "\\part{Book}\n\\chapter{Chapter}\n\\begin{theorem}[Main result]\nTrue.\\end{theorem}\n"
    blocks = walk.blocks_for(text, file_rel="B.tex", repo_file="B.tex", md=__import__('pathlib').Path('.'), corpus="", dir_param="", para_spans=[], known_macros=frozenset())
    assert [b['kind'] for b in blocks] == ['head','head','theorem']
    assert blocks[-1]['title'] == 'Main result'
    assert walk._flatten_pieces(blocks[-1]['pieces']).strip() == 'True.'


def test_inline_environment_bodies_are_not_dropped():
    text = ("\\begin{theorem}[Inline]True with $x$.\\end{theorem}\n"
            "\\begin{equation}E=mc^2\\end{equation}\n"
            "\\begin{itemize}\\item First item.\\end{itemize}\n")
    blocks = walk.blocks_for(text, file_rel="inline.tex", repo_file="inline.tex", md=Path('.'),
                             corpus="", dir_param="", para_spans=[], known_macros=frozenset())
    assert [block["kind"] for block in blocks] == ["theorem", "equation", "list"]
    assert walk._flatten_pieces(blocks[0]["pieces"]).strip() == "True with $x$."
    assert blocks[1]["math"] == "E=mc^2"
    assert walk._flatten_pieces(blocks[2]["items"][0]["pieces"]).strip() == "First item."


def test_table_wrapper_caption_escaped_ampersand_math_and_multicolumn():
    text = ("\\begin{table}[t]\n\\centering\n"
            "\\caption{A \\textbf{careful} table with $x$.}\n\\label{tab:careful}\n"
            "\\begin{tabular}{lll}\n\\toprule\n"
            "\\textbf{Name} & \\textbf{Expression} & \\textbf{Note} \\\\\n"
            "\\midrule\n"
            "A \\& B & $f(a & b)$ & \\multicolumn{1}{c}{kept \\& joined} \\\\\n"
            "\\multicolumn{2}{c}{Combined $x & y$} & Tail \\\\\n"
            "\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    block = walk.blocks_for(text, file_rel="table.tex", repo_file="table.tex", md=Path('.'),
                            corpus="", dir_param="", para_spans=[], known_macros=frozenset())[0]
    assert block["kind"] == "table" and block["env"] == "table"
    assert block["caption"] == "A \\textbf{careful} table with $x$."
    assert walk._flatten_pieces(block["caption_pieces"]) == "A careful table with $x$."
    assert len(block["rows"]) == 3 and block["rows"][0]["header"] is True
    assert [cell["tex"] for cell in block["rows"][1]["cells"]] == [
        "A \\& B", "$f(a & b)$", "kept \\& joined"]
    assert block["rows"][2]["cells"][0]["colspan"] == 2
    assert block["rows"][2]["cells"][0]["tex"] == "Combined $x & y$"
    assert all(block["tex"][cell["o_start"]:cell["o_end"]] == cell["tex"]
               for row in block["rows"] for cell in row["cells"])
    assert all("caption" not in cell["tex"] and "tabular" not in cell["tex"]
               for row in block["rows"] for cell in row["cells"])


def test_real_corpus_table_has_only_cells_and_caption():
    source = Path("synthetics papers/adaptive-normal-form/manuscript/tex/sections/01_introduction.tex")
    blocks = walk.blocks_for(source.read_text(encoding="utf-8"), file_rel=source.name,
                             repo_file=source.as_posix(), md=source.parent, corpus="", dir_param="",
                             para_spans=[], known_macros=frozenset())
    table = next(block for block in blocks if block["kind"] == "table")
    assert table["caption"].startswith("Five instances of the adaptive normal form")
    assert len(table["rows"]) == 6
    assert [cell["tex"] for cell in table["rows"][0]["cells"]][:2] == [
        "\\textbf{System}", "\\textbf{Mandate $\\theta$}"]
    assert all("\\begin" not in cell["tex"] and "\\caption" not in cell["tex"]
               for row in table["rows"] for cell in row["cells"])


def test_malformed_table_falls_back_whole_with_caption_preserved():
    text = ("\\begin{table}\n\\caption{Still readable.}\n"
            "\\begin{tabular}{cc}\na & {broken \\\\n\\end{table}\n")
    block = walk.blocks_for(text, file_rel="bad.tex", repo_file="bad.tex", md=Path('.'),
                            corpus="", dir_param="", para_spans=[], known_macros=frozenset())[0]
    assert block["kind"] == "raw"
    assert block["caption"] == "Still readable."
    assert "table grammar could not be parsed safely" in block["reason"]
    assert "\\begin{tabular}" in block["tex"]


def test_walk_client_carries_and_renders_structured_table_cells():
    module = walk_source()
    assert "rows: Array.isArray(b.rows) ? b.rows : null" in module
    assert "cellSpec.pieces" in module and "renderPiecesMapped(cellSpec.pieces" in module
    assert "td.colSpan" in module and "b.caption_pieces" in module

def test_graphicspath_resolves_declared_figure_without_fallback(tmp_path):
    (tmp_path/'figures').mkdir(); (tmp_path/'figures'/'real.pdf').write_bytes(b'%PDF-1.4')
    (tmp_path/'main.tex').write_text('\\graphicspath{{figures/}}')
    blocks=walk.blocks_for('\\begin{figure}\\includegraphics{real}\\end{figure}',file_rel='x.tex',repo_file='x.tex',md=tmp_path,corpus='',dir_param='',para_spans=[],known_macros=frozenset())
    assert blocks[0]['images'][0]['exists'] and blocks[0]['images'][0]['file']=='figures/real.pdf'


def _projected(text, macros=None):
    return walk.blocks_for(text, file_rel='sample.tex', repo_file='sample.tex', md=Path('.'),
                           corpus='', dir_param='', para_spans=[], known_macros=macros or {})


def _pieces(value):
    if isinstance(value, dict):
        if 't' in value:
            yield value
        for child in value.values():
            yield from _pieces(child)
    elif isinstance(value, list):
        for child in value:
            yield from _pieces(child)


def test_environment_body_does_not_swallow_title_or_first_group():
    block = _projected(r'\begin{theorem}[A {nested} title]{The first group} survives.\end{theorem}')[0]
    assert block['title'] == 'A {nested} title'
    assert 'The first group survives.' == walk._flatten_pieces(block['pieces'])
    assert '{The first group}' in block['tex']  # TeX grouping stays in source, not reader prose
    proof = _projected(r'\begin{proof}[Proof of \Cref{thm:kept}]The proof.\end{proof}')[0]
    reference = next(p for p in proof['title_pieces'] if p['t'] == 'ref')
    assert reference['label'] == 'thm:kept'
    assert proof['tex'][reference['o_start']:reference['o_end']] == r'\Cref{thm:kept}'


def test_real_explanation_uses_authored_title_and_declared_labels():
    source = Path('synthetics papers/corpus-as-a-state/manuscript/main.tex').read_text()
    start = source.index(r'\begin{explained}{The density operator}')
    end = source.index(r'\end{explained}', start) + len(r'\end{explained}')
    text = source[start:end]
    block = _projected(text, walk._macros_from(source))[0]
    assert block['title'] == 'The density operator'
    labels = [p for p in block['pieces'] if p['t'] == 'semantic-label']
    assert [walk._flatten_pieces(p['pieces']) for p in labels] == [
        'What it says.', 'Why it is true.', 'What it buys here.']
    assert not [p for p in _pieces(block) if p['t'] == 'macro']
    assert block['tex'] == text
    assert [text[p['o_start']:p['o_end']].strip() for p in labels] == [r'\says', r'\why', r'\buys']


def test_nested_lists_and_equations_inside_theorem_keep_source_addresses():
    text = (r'\begin{theorem}[Nested]' '\n'
            r'Before.\begin{enumerate}[label=(\roman*),leftmargin=2em]' '\n'
            r'\item First $x$.\begin{itemize}\item Inner.\begin{enumerate}[label=\alph*]' '\n'
            r'\item Deep $y$.\end{enumerate}\end{itemize}' '\n'
            r'\item Second.\begin{equation}z=x+y\end{equation}\end{enumerate}' '\n'
            r'After.\end{theorem}')
    block = _projected(text)[0]
    assert block['tex'] == text
    listing = next(p for p in block['pieces'] if p['t'] == 'list')
    assert len(listing['items']) == 2
    assert 'Inner.' in listing['items'][0]['sub']['items'][0]['tex']
    assert not [p for p in _pieces(block) if p['t'] == 'macro']
    for p in _pieces(block):
        assert 0 <= p['o_start'] <= p['o_end'] <= len(text)
        if p['t'] == 'math':
            span = text[p['o_start']:p['o_end']]
            assert p['s'] in span
    assert any(p['t'] == 'math' and p['s'] == 'z=x+y' for p in _pieces(block))


def test_real_algorithm_retains_caption_conditions_results_and_controls():
    source = Path('synthetics papers/corpus-as-a-state/manuscript/main.tex').read_text()
    start = source.index(r'\begin{algorithm}')
    end = source.index(r'\end{algorithm}', start) + len(r'\end{algorithm}')
    block = _projected(source[start:end], walk._macros_from(source))[0]
    assert block['title'].startswith(r'\textsc{ascend}')
    typed = list(_pieces(block))
    assert any(p['t'] == 'algorithm' for p in typed)
    assert {'Require: ', 'Ensure: ', 'if ', 'else', 'end if', 'return '} <= {
        p['s'] for p in typed if p['t'] == 'algorithm-keyword'}
    assert any(p['t'] == 'math' and p['s'] == 'M<d' for p in typed)
    assert any(p['t'] == 'ref' and p['label'] == 'lem:S4-gram' for p in typed)
    assert not [p for p in typed if p['t'] == 'macro']


def test_declared_unresolved_values_are_not_fabricated_or_hidden():
    tex = r'Measurement: \num{b3.bound.violations}; omission \ldots.'
    pieces = walk.tex_pieces(tex, {r'\num': r'\textcolor{red}{\texttt{[#1]}}'})
    pending = next(p for p in pieces if p['t'] == 'placeholder')
    assert pending['key'] == 'b3.bound.violations'
    assert tex[pending['o_start']:pending['o_end']] == r'\num{b3.bound.violations}'
    assert 'unresolved' in pending['reason']
    assert walk.tex_pieces(r'\num{1.25}', {})[0]['t'] == 'macro'


def test_hydrated_math_rebuilds_following_text_source_map():
    """Run the actual map updater over stable hosts with changed math content."""
    import json
    import subprocess
    module = walk_source()
    start = module.index('function refreshPieceMap(')
    end = module.index('/** A map is usable', start)
    # M5 S3: refreshPieceMap reads through the walk's ONE reader, readableDOM (walk-selection.mjs), which the
    # updater's own slice does not contain. Its real declarations are bound verbatim (that module imports the
    # DOM-holding walk owners and cannot load in node), over inline-element doubles with the reader's interface.
    script = module[start:end] + walk_declarations('isChrome', 'readableDOM') + r'''
      const text=s=>({nodeType:3,nodeValue:s,parentNode:null,get parentElement(){return this.parentNode;}});
      const element=children=>{const n={nodeType:1,tagName:'SPAN',children,parentNode:null,get childNodes(){return this.children;},
        matches:()=>false,closest:()=>null};children.forEach(c=>c.parentNode=n);return n;};
      const before=text('Before '),math=element([text('x^2')]),after=text(' after');
      const host=element([before,math,after]);
      const map=[{t:'text',nodes:[before]},{t:'math',nodes:[math]},{t:'text',nodes:[after]}];
      const block={bodyEl:host,pieceMap:map};refreshPieceMap(block);
      const original=map.map(p=>[p.rStart,p.rEnd,p.rText]);
      math.children=[text('x'),text('2')];math.children.forEach(c=>c.parentNode=math);
      refreshPieceMap(block);
      console.log(JSON.stringify({original,hydrated:map.map(p=>[p.rStart,p.rEnd,p.rText])}));
    '''
    result = subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,check=True)
    got=json.loads(result.stdout)
    assert got['original'] == [[0,7,'Before '],[7,10,'x^2'],[10,16,' after']]
    assert got['hydrated'] == [[0,7,'Before '],[7,9,'x2'],[9,15,' after']]


def test_root_plumbing_prefix_never_discards_authored_prose():
    source = ('\\begin{document}\n\\noindent Substantive opening.\n'
              '\\clearpage Continued explanation.\n\\bibliographystyle{plain}\n\\end{document}')
    masked, _ = walk.root_content(source)
    assert masked.splitlines()[1] == source.splitlines()[1]
    assert masked.splitlines()[2] == source.splitlines()[2]
    assert masked.splitlines()[3] == ''
    assert walk._flatten_pieces(walk.tex_pieces(r'\noindent {Grouped prose}')) == 'Grouped prose'
    real = Path('synthetics papers/superarc/manuscript/main.tex').read_text()
    projected, _ = walk.root_content(real)
    authored = [line for line in real.splitlines() if line.lstrip().startswith(r'\noindent')]
    assert authored and all(line in projected for line in authored)


def test_pdf_figure_cleanup_uses_the_loading_task_contract():
    import json
    import subprocess
    module=walk_source()
    function=next(line for line in module.splitlines() if line.startswith('function releaseFigure('))
    script=function+'''
      let cancelled=0,destroyed=0;
      releaseFigure({task:{cancel(){cancelled++;}},loading:{destroy(){destroyed++;return Promise.resolve();}},doc:{}});
      releaseFigure({doc:{}});
      await Promise.resolve();console.log(JSON.stringify({cancelled,destroyed}));
    '''
    result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)=={'cancelled':1,'destroyed':1}


def test_declared_environment_from_input_preamble_is_source_mapped_and_renamable(tmp_path):
    from laplace.manuscript import manuscript_figure_preview
    root = tmp_path / "Book.tex"
    preamble = tmp_path / "preamble.tex"
    root.write_text("\\documentclass{book}\n\\input{preamble}\n\\begin{document}\n\\end{document}\n")
    preamble.write_text("\\newtcolorbox{workedcase}[1]{title={Worked: #1}}\n")
    declared = manuscript_figure_preview.declared_environments(root, tmp_path)
    text = "\\begin{workedcase}{Renamed}\nWords with $x$.\n\\end{workedcase}\n"
    block = walk.blocks_for(text, file_rel="chapter.tex", repo_file="chapter.tex", md=tmp_path,
                            corpus="", dir_param="", para_spans=[], known_macros={},
                            declared_envs=declared,
                            declared_presentation=manuscript_figure_preview.declared_environment_presentation(root, tmp_path))[0]
    assert declared == {"workedcase": "tcolorbox"}
    assert block["kind"] == "custom" and block["custom_kind"] == "tcolorbox"
    assert block["title"] == "Renamed"
    assert block["title_prefix"] == "Worked: " and block.get("title_suffix") == ""
    assert walk._flatten_pieces(block["title_pieces"]) == "Renamed"
    assert "Words with $x$." == walk._flatten_pieces(block["pieces"]).strip()


def test_synthetics_operationalexample_is_source_mapped_and_previewable():
    document = walk.doc("synthetics-master-guide")
    block = next(block for section in document["sections"] for block in section["blocks"]
                 if block.get("env") == "operationalexample")
    assert block["kind"] == "custom" and block["custom_kind"] == "tcolorbox"
    assert block["title"] == "Composing two small alphabets"
    assert block["title_prefix"] == "Operational example: " and block.get("title_suffix") == ""
    assert walk._flatten_pieces(block["title_pieces"]) == "Composing two small alphabets"
    assert "The twelve pairs have composite ranks" in walk._flatten_pieces(block["pieces"])
    assert "environment=operationalexample" in block["preview_image"]
    assert block["presentation"] == {"colback": "white", "colframe": "#477363",
                                     "colbacktitle": "#477363"}
    assert document["refs"]["eq:log-rank"] == "1.6"


def test_one_line_equation_with_label_is_a_source_mapped_block():
    text = r"\begin{equation} C G = H C \label{eq:closure}\end{equation}"
    block = walk.blocks_for(text, file_rel="one.tex", repo_file="one.tex", md=Path("."),
                            corpus="", dir_param="", para_spans=[], known_macros={})[0]
    assert block["kind"] == "equation" and block["labels"] == ["eq:closure"]
    assert block["src"]["line_start"] == block["src"]["line_end"] == 1
    assert block["math"].strip() == "C G = H C"


def test_doc_preserves_one_line_root_equation_for_picker(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface
    manuscript = tmp_path / "manuscript"
    manuscript.mkdir()
    (manuscript / "main.tex").write_text(
        "\\documentclass{book}\n\\begin{document}\n\\chapter{Root}\n"
        "\\begin{equation} C G_\\mu = G_M C \\label{eq:closure}\\end{equation}\n"
        "\\begin{thebibliography}{9}\n\\bibitem{Landauer1961} R. Landauer. Heat cost. 1961.\n"
        "\\end{thebibliography}\n"
        "\\end{document}\n", encoding="utf-8")
    (manuscript / "main.aux").write_text("\\newlabel{eq:closure}{{1.1}{1}}\n"
                                            "\\bibcite{Landauer1961}{1}\n", encoding="utf-8")
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda corpus, directory: manuscript)
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)

    document = walk.doc()
    equation = next(block for section in document["sections"] for block in section["blocks"]
                    if block.get("kind") == "equation")

    assert equation["labels"] == ["eq:closure"]
    assert equation["src"]["line_start"] == equation["src"]["line_end"] == 4
    assert equation["number"] == "1.1"
    assert document["citations"]["Landauer1961"]["num"] == "1"
    assert document["citations"]["Landauer1961"]["entry"].startswith("R. Landauer")
    assert document["citation_targets"][0]["title"] == "R. Landauer. Heat cost. 1961."


def test_client_normalization_keeps_backend_equation_number():
    module = walk_source()
    assert "number: (typeof b.number" in module


def test_generic_renamed_environment_is_marked_for_compiled_preview(tmp_path):
    from laplace.manuscript import manuscript_figure_preview
    root = tmp_path / "Book.tex"
    root.write_text("\\documentclass{book}\n"
                    "\\newenvironment{remarkbox}{\\begin{quote}}{\\end{quote}}\n"
                    "\\begin{document}\n\\end{document}\n")
    declared = manuscript_figure_preview.declared_environments(root, tmp_path)
    text = "\\begin{remarkbox}Visible through the original class.\\end{remarkbox}\n"
    block = walk.blocks_for(text, file_rel="chapter.tex", repo_file="chapter.tex", md=tmp_path,
                            corpus="", dir_param="", para_spans=[], known_macros={},
                            declared_envs=declared)[0]
    assert declared["remarkbox"] == "compiled"
    assert block["kind"] == "custom" and block["custom_kind"] == "compiled"
    assert "Visible through the original class." in walk._flatten_pieces(block["pieces"])


def test_balanced_class_environment_without_declaration_is_compiled_block():
    text = "\\begin{minipage}{\\linewidth}\nVisible class body.\n\\end{minipage}\n"
    block = walk.blocks_for(text, file_rel="chapter.tex", repo_file="chapter.tex", md=Path("."),
                            corpus="", dir_param="", para_spans=[], known_macros={})[0]
    assert block["kind"] == "custom" and block["custom_kind"] == "compiled"
    assert "Visible class body." in walk._flatten_pieces(block["pieces"])


def test_declared_newtheorem_names_shared_counters_and_optional_titles_keep_exact_source(tmp_path):
    from laplace.manuscript import manuscript_figure_preview as preview
    root = tmp_path / 'Book.tex'
    root.write_text('\\documentclass{book}\n\\input{definitions}\n\\begin{document}\n\\end{document}\n')
    (tmp_path / 'definitions.tex').write_text(
        '% \\newtheorem{ignored}{Wrong}\n'
        '\\newtheorem{claimLedger2}{\\textbf{Theorem}}[chapter]\n'
        '\\newtheorem{consequenceX}[claimLedger2]{Proposition}\n'
        '\\newtheorem{workedRiddle}{Exercise}[section]\n'
        '\\newtheorem*{freeObservation}{Observation}\n')
    declarations = preview.declared_environments(root, tmp_path)
    styles = preview.declared_environment_presentation(root, tmp_path)
    assert 'ignored' not in declarations
    assert styles['claimLedger2']['within_counter'] == 'chapter'
    assert styles['consequenceX']['counter'] == 'claimLedger2'
    assert styles['freeObservation']['numbered'] == 'false'
    for environment, label in [('claimLedger2','Theorem'),('workedRiddle','Exercise'),('freeObservation','Observation')]:
        body = '\\begin{'+environment+'}{Initial group} remains.\\end{'+environment+'}'
        projected = walk.blocks_for(body, file_rel='chapter.tex', repo_file='chapter.tex', md=tmp_path,
            corpus='', dir_param='', para_spans=[], known_macros={},
            declared_envs=declarations, declared_presentation=styles)[0]
        assert projected['kind'] == 'theorem' and projected['theorem_label'] == label
        assert 'Initial group remains.' == walk._flatten_pieces(projected['pieces'])
        assert '{Initial group}' in projected['tex']
    text = ('\\begin{consequenceX}[A {nested} \\emph{title}]\n'
            '\\label{prop:one}\nThe first {group} stays in the body.\n\\end{consequenceX}')
    block = walk.blocks_for(text, file_rel='chapter.tex', repo_file='chapter.tex', md=tmp_path,
        corpus='', dir_param='', para_spans=[], known_macros={},
        declared_envs=declarations, declared_presentation=styles)[0]
    assert block['kind'] == 'theorem' and block['theorem_label'] == 'Proposition'
    assert block['theorem_optional_title'] is True
    assert block['number_labels'] == ['prop:one']
    assert walk._flatten_pieces(block['title_pieces']) == 'A nested title'
    assert '[A ' not in walk._flatten_pieces(block['pieces'])
    assert 'The first group stays in the body.' in walk._flatten_pieces(block['pieces'])
    assert block['tex'] == text and block['src']['line_start'] == 1
    assert block['src']['line_end'] == 4
    emphasis = next(piece for piece in _pieces(block['title_pieces']) if piece.get('t') == 'emph')
    assert text[emphasis['o_start']:emphasis['o_end']] == r'\emph{title}'


def test_declared_theorem_numbers_use_only_available_own_aux_labels(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface
    manuscript = tmp_path / 'manuscript'; manuscript.mkdir()
    (manuscript / 'main.tex').write_text(
        '\\documentclass{book}\n'
        '\\newtheorem{axiomBundle}{Theorem}[chapter]\n'
        '\\newtheorem{sharedResult}[axiomBundle]{Proposition}\n'
        '\\newtheorem*{freeRemark}{Remark}\n'
        '\\begin{document}\n\\chapter{One}\n'
        '\\begin{axiomBundle}[Named result]\\label{thm:named}Statement.\\end{axiomBundle}\n'
        '\\begin{sharedResult}\\label{prop:shared}Other statement.\\end{sharedResult}\n'
        '\\begin{axiomBundle}No own label.\n\\begin{equation}x=1\\label{eq:inside}\\end{equation}\n\\end{axiomBundle}\n'
        '\\begin{freeRemark}\\label{remark:free}Unnumbered.\\end{freeRemark}\n'
        '\\end{document}\n')
    aux = manuscript / 'main.aux'
    aux.write_text('\\newlabel{thm:named}{{1.3}{1}}\n\\newlabel{prop:shared}{{1.4}{1}}\n'
                   '\\newlabel{eq:inside}{{9.9}{1}}\n\\newlabel{remark:free}{{1.4}{1}}\n')
    monkeypatch.setattr(review_surface, 'manuscript_dir', lambda corpus, directory: manuscript)
    monkeypatch.setattr(walk, '_repo_root', lambda: tmp_path)
    blocks = [block for section in walk.doc()['sections'] for block in section['blocks'] if block['kind'] == 'theorem']
    assert [(block['theorem_label'],block.get('number')) for block in blocks] == [
        ('Theorem','1.3'),('Proposition','1.4'),('Theorem',None),('Remark',None)]
    assert blocks[0]['title'] == 'Named result'
    aux.unlink()
    blocks = [block for section in walk.doc()['sections'] for block in section['blocks'] if block['kind'] == 'theorem']
    assert all(not block.get('number') for block in blocks)


def test_nested_numbered_equations_keep_compiled_label_identity_and_exact_theorem_source_offsets():
    text = r'''\begin{theorem}[Projected evolution]
\label{thm:projection}
For the stated assumptions,
\begin{equation}
\begin{aligned}
 u'(t)&=Au(t)+\int_0^t K(t-s)u(s)\,ds\\
 K(t)&=Be^{tD}C.
\end{aligned}
\label{eq:projection}
\end{equation}
The conclusion follows.
\end{theorem}'''
    block = walk.blocks_for(text, file_rel='theory.tex', repo_file='theory.tex', md=Path('.'),
                            corpus='', dir_param='', para_spans=[], known_macros=frozenset())[0]
    equation = next(piece for piece in block['pieces'] if piece.get('env') == 'equation')
    assert block['number_labels'] == ['thm:projection']
    assert equation['labels'] == ['eq:projection']
    assert equation['display'] is True and '\\label' not in equation['s']
    assert block['tex'][equation['o_start']:equation['o_end']] == text[text.index(r'\begin{equation}'):text.index(r'\end{equation}') + len(r'\end{equation}')]
    refs, _ = walk.parse_aux(r'\newlabel{thm:projection}{{7.4}{12}}\newlabel{eq:projection}{{7.31}{12}}')
    assert refs[equation['labels'][0]] == '7.31' and refs[block['number_labels'][0]] == '7.4'


def test_multiline_equation_rows_preserve_label_positions_without_a_second_source_copy():
    text = '\\begin{align}\n𝓗 &= A \\label{eq:first}\\\\\nB &= C \\label{eq:second}\n\\end{align}'
    block = walk.blocks_for(text, file_rel='theory.tex', repo_file='theory.tex', md=Path('.'),
                            corpus='', dir_param='', para_spans=[], known_macros=frozenset())[0]
    assert [row['label'] for row in block['equation_labels']] == ['eq:first', 'eq:second']
    before = block['math'][:block['math'].index(r'\\')]
    assert block['equation_labels'][0]['offset'] == len(before.encode('utf-16-le')) // 2
    assert block['tex'] == text and '\\label' not in block['math']


def test_display_delimiters_own_nested_arrays_and_leave_no_literal_closing_block():
    for opening, closing in [(r'\[', r'\]'), ('$$', '$$')]:
        display = opening + '\n' + r'\begin{array}{rrr}' + '\n' + r'20&400&0.00244002\\' + '\n' + r'5&25&0.03305691' + '\n' + r'\end{array}' + '\n' + closing
        source = 'Before.\n\n' + display + '\nAfter.'
        blocks = walk.blocks_for(source, file_rel='array.tex', repo_file='array.tex', md=Path('.'),
                                 corpus='', dir_param='', para_spans=[], known_macros=frozenset())
        assert [row['kind'] for row in blocks] == ['para', 'equation', 'para']
        equation = blocks[1]
        assert equation['env'] == 'displaymath' and equation['number'] is None
        assert equation['tex'] == display
        assert r'\begin{array}{rrr}' in equation['math']
        assert opening not in equation['math'] and closing not in equation['math']
        assert equation['src']['line_start'] == 3 and equation['src']['line_end'] == 8


def test_display_same_line_tail_and_eqref_command_remain_source_faithful():
    text = r'\[\begin{array}{cc}a&b\end{array}\] Then \eqref{eq:answer}.'
    blocks = walk.blocks_for(text, file_rel='tail.tex', repo_file='tail.tex', md=Path('.'),
                            corpus='', dir_param='', para_spans=[], known_macros=frozenset())
    assert len(blocks) == 1 and blocks[0]['kind'] == 'para'
    reference = next(piece for piece in blocks[0]['pieces'] if piece['t'] == 'ref')
    assert reference['cmd'] == 'eqref'
    assert text[reference['o_start']:reference['o_end']] == r'\eqref{eq:answer}'

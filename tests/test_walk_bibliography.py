from pathlib import Path
from laplace.manuscript import walk


def blocks(source):
    return walk.blocks_for(source,file_rel='references.tex',repo_file='references.tex',md=Path('.'),
        corpus='',dir_param='',para_spans=[],known_macros=frozenset())


def test_authored_bibliography_is_a_source_mapped_list_not_a_theorem():
    source=('\\begin{thebibliography}{99}\n'
        '\\bibitem{first} A. Author. \\emph{A title}. \\newblock With $x^2$. 2020.\n'
        '\\bibitem[Second(2021)]{second} B. Author. Second title.\n'
        '\\end{thebibliography}')
    item=blocks(source)[0]
    assert item['kind']=='list' and item['env']=='thebibliography' and item['title']=='References'
    assert item['tex']==source and item['src']['line_start']==1 and item['src']['line_end']==4
    assert [row['key'] for row in item['items']]==['first','second']
    assert [row['term'] for row in item['items']]==['1','Second(2021)']
    assert '\\bibitem' not in walk._flatten_pieces(item['items'][0]['pieces'])
    assert '\\newblock' not in walk._flatten_pieces(item['items'][0]['pieces'])
    emphasis=next(piece for piece in item['items'][0]['pieces'] if piece['t']=='emph')
    assert source[emphasis['o_start']:emphasis['o_end']]==r'\emph{A title}'
    label=item['items'][1]['term_pieces'][0]
    assert source[label['o_start']:label['o_end']]=='Second(2021)'
    for entry in item['items']:
        assert source[entry['o_start']:entry['o_end']]==entry['tex']


def test_comments_and_nested_bibitem_text_cannot_create_extra_entries():
    source=('\\begin{thebibliography}{9}\n% \\bibitem{commented} ignored\n'
        '\\bibitem{actual} Description with \\texttt{\\bibitem{literal}}.\n'
        '\\end{thebibliography}')
    assert [row['key'] for row in blocks(source)[0]['items']]==['actual']


def test_empty_bibliography_and_malformed_entry_are_distinguished():
    empty=blocks('\\begin{thebibliography}{9}\n% no entries\n\\end{thebibliography}')[0]
    assert empty['kind']=='list' and empty['items']==[]
    malformed=blocks('\\begin{thebibliography}{9}\n\\bibitem No key.\n\\end{thebibliography}')[0]
    assert malformed['kind']=='raw' and 'No key.' in malformed['tex']


def test_newblock_spacing_is_readable_and_retains_its_exact_source_span():
    source=r"First.\newblock Second."
    pieces=walk.tex_pieces(source)
    assert walk._flatten_pieces(pieces)=='First. Second.'
    separator=next(piece for piece in pieces if piece['t']=='symbol')
    assert source[separator['o_start']:separator['o_end']]==r"\newblock "

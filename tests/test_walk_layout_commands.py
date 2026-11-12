from laplace.manuscript.walk import tex_pieces

def test_layout_commands_preserve_visible_text_without_raw_macros():
    pieces=tex_pieces(r"\small A\hspace{2em}\ttfamily B\itshape C\quad D\phantom{gone}E\begingroup F\endgroup")
    text=''.join(p.get('s','') for p in pieces if p['t']=='text')
    assert 'A' in text and 'B' in text and 'C' in text and 'D' in text and 'E' in text and 'F' in text
    assert not any(p['t']=='macro' for p in pieces)


def test_frontmatter_presentation_arguments_and_groups_preserve_visible_content_and_offsets():
    source = r'\thispagestyle{empty}\vspace*{\fill}{\large\color[HTML]{123456}A scientific title}\par \textcolor{blue}{Keep $x$ and \emph{its meaning}}. \hypersetup{pageanchor=false}'
    pieces = tex_pieces(source)
    from laplace.manuscript.walk import _flatten_pieces
    visible = _flatten_pieces(pieces)
    assert 'A scientific title' in visible and 'Keep $x$ and its meaning' in visible
    assert 'empty' not in visible and '123456' not in visible and 'pageanchor' not in visible
    assert not any(piece['t'] == 'macro' for piece in pieces)
    def visit(rows):
        for piece in rows:
            assert 0 <= piece['o_start'] <= piece['o_end'] <= len(source)
            if piece.get('t') == 'presentation':
                assert source[piece['o_start']:piece['o_end']].startswith('\\'+piece['name'])
            visit(piece.get('pieces') or [])
    visit(pieces)
    assert any(p['t']=='macro' and p['name']=='scientificMeaning' for p in tex_pieces(r'\scientificMeaning{Keep all of this}'))
    assert any(p['t']=='macro' for p in tex_pieces(r'\hypersetup missing braces'))
    assert _flatten_pieces(tex_pieces(r'Literal \{a,b\}')) == 'Literal {a,b}'


def test_presentation_only_blocks_keep_exact_source_and_href_text_is_not_raw_tex():
    from pathlib import Path
    from laplace.manuscript.walk import blocks_for, _flatten_pieces
    source = '\\color{ink}\n\\hypersetup{pageanchor=false}\n\n' + r'\noindent{\large A title}\par The \href{notes.md}{numerical notes} and \url{https://example.org/source} remain readable.'
    blocks = blocks_for(source,file_rel='main.tex',repo_file='main.tex',md=Path('.'),corpus='',dir_param='',para_spans=[],known_macros=frozenset())
    assert blocks[0]['presentation_only'] is True
    assert blocks[0]['tex'] == '\\color{ink}\n\\hypersetup{pageanchor=false}'
    assert blocks[0]['src']['line_start']==1 and blocks[0]['src']['line_end']==2
    assert blocks[1]['presentation_only'] is False
    assert 'A title' in _flatten_pieces(blocks[1]['pieces'])
    href=next(p for p in blocks[1]['pieces'] if p['t']=='href')
    assert href['url']=='notes.md' and href['s']=='numerical notes'
    assert blocks[1]['tex'][href['o_start']:href['o_end']] == r'\href{notes.md}{numerical notes}'

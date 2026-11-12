from pathlib import Path
from walk_source import walk_source
from urllib.parse import urlparse, parse_qs

from laplace.manuscript import walk, review_surface
from laplace.projects import library as writing_projects
from laplace.pipeline import registry


def test_named_book_preamble_is_consumed_but_not_rendered_as_front_matter(tmp_path,monkeypatch):
    source=tmp_path/'book';source.mkdir()
    (source/'Synthetics.tex').write_text('% A preamble comment\n\\documentclass{book}\n\\input{preamble}\n\\begin{document}\n\\frontmatter\n\\mainmatter\n\\input{chapter}\n\\end{document}\n')
    (source/'preamble.tex').write_text('\\usepackage{amsmath}\n\\newcommand{\\example}{Never prose}\n')
    (source/'chapter.tex').write_text('\\chapter{A real chapter}\nVisible content.\n')
    monkeypatch.setattr(walk,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(registry,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    status,_=writing_projects.import_source({'name':'named-book','title':'Synthetics','root':'book/Synthetics.tex','editable':True},root=tmp_path)
    assert status==201
    model=walk.doc('named-book')
    content='\n'.join(b['tex'] for s in model['sections'] for b in s['blocks'])
    assert 'Visible content.' in content
    assert 'usepackage' not in content and 'Never prose' not in content
    assert '\\frontmatter' not in content and '\\mainmatter' not in content
    assert 'preamble.tex' in model['source_file_revisions']


def test_imported_manuscript_serves_exact_parent_directory_graphics(tmp_path, monkeypatch):
    source = tmp_path / 'research/paper/manuscript/tex'
    figures = tmp_path / 'research/paper/scripts/figs'
    source.mkdir(parents=True)
    figures.mkdir(parents=True)
    image = b'\x89PNG\r\n\x1a\nfixture image'
    (figures / 'a.png').write_bytes(image)
    (figures / 'b.png').write_bytes(image + b'b')
    (figures / 'not-declared.png').write_bytes(image + b'private')
    (source / 'main.tex').write_text(
        '\\documentclass{article}\n\\begin{document}\n\\section{Evidence}\n'
        '\\begin{figure}\n\\includegraphics{../../scripts/figs/a.png}\n'
        '\\includegraphics{../../scripts/figs/b.png}\n\\caption{Both panels.}\n'
        '\\end{figure}\n\\end{document}\n')
    monkeypatch.setattr(walk, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(registry, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(review_surface, '_repo_root', lambda: tmp_path)
    status, result = writing_projects.import_source({'name': 'imported', 'title': 'Imported',
        'root': 'research/paper/manuscript/tex/main.tex', 'editable': True}, root=tmp_path)
    assert status == 201, result
    document = walk.doc('imported')
    figure = next(b for s in document['sections'] for b in s['blocks'] if b['kind'] == 'figure')
    assert len(figure['images']) == 2
    for entry in figure['images']:
        assert entry['exists']
        response = walk.handle('/walk/asset', parse_qs(urlparse(entry['route']).query), 'GET', b'')
        assert response[0:2] == (200, 'image/png')
        assert response[2].startswith(image)
    # Importing one manuscript does not open the rest of the repository's images.
    assert walk.asset('imported', '', '', 'research/paper/scripts/figs/not-declared.png')[0] == 403
    assert walk.asset('imported', '', '', '../outside.png')[0] == 403


def test_walk_preserves_every_declared_figure_panel_in_consumer():
    module = walk_source()
    assert 'images: Array.isArray(b.images) ? b.images : []' in module
    assert 'for(const [index,image]of b.images.entries())' in module

"""A publication edition opens on its own visible title with its companion navigation on the same page.

Public synthetic masters only (book and article, with no opening, an explicit \\maketitle or a custom
titlepage), three chapter inputs, shared references and three edition declarations, built by the real
compiler through the existing edition owners and read page by page from the rendered PDF.
"""
import shutil
import subprocess

import pytest

import test_publication_editions as t
from test_publication_editions import fixture  # noqa: F401  (the shared public synthetic project fixture)

CHAPTERS = {name: '\\chapter{' + name.capitalize() + ' chapter}\\label{ch:' + name + '}\n'
            + name.capitalize() + 'only marker paragraph. \\fixtureterm. See \\cite{shared2026}.\n' for name in t.NAMES}
BODY = '\\input{chapters/alpha}\n\\input{chapters/beta}\n\\input{chapters/gamma}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n'
MASTERS = {
    'book-no-opening': '\\documentclass{book}\n\\input{preamble}\n\\title{Master Book Title}\n\\begin{document}\n' + BODY,
    'article-no-opening': '\\documentclass{article}\n\\input{preamble}\n\\title{Master Article Title}\n\\begin{document}\n'
                          + BODY.replace('\\chapter', '\\section'),
    'book-explicit-maketitle': '\\documentclass{book}\n\\input{preamble}\n\\title{Master Book Title}\n\\author{Fixture Author}\n'
                               '\\date{Fixture date}\n\\begin{document}\n\\maketitle\n' + BODY,
    'book-titlepage': '\\documentclass{book}\n\\input{preamble}\n\\begin{document}\n\\begin{titlepage}\n'
                      '\\centering Fixture House Imprint\\par\n\\end{titlepage}\n' + BODY,
    # The same title page written inline: begin, content and end on one line (OPEN-R1).
    'book-inline-titlepage': '\\documentclass{book}\n\\input{preamble}\n\\begin{document}\n'
                             '\\begin{titlepage}\\centering Fixture House Imprint\\par\\end{titlepage}\n' + BODY,
    'article-inline-titlepage': '\\documentclass{article}\n\\input{preamble}\n\\begin{document}\n'
                                '\\begin{titlepage}\\centering Fixture House Imprint\\par\\end{titlepage}\n'
                                + BODY.replace('\\chapter', '\\section'),
}


def _tools():
    return all(shutil.which(tool) for tool in ('pdftotext', 'pdfinfo', 'qpdf')) and t._tex_available()


def pages(pdf):
    count = int(next(line.split()[-1] for line in subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True,
                                                                  check=True).stdout.splitlines() if line.startswith('Pages:')))
    return [subprocess.run(['pdftotext', '-f', str(n), '-l', str(n), '-layout', str(pdf), '-'], capture_output=True,
                           text=True, check=True).stdout for n in range(1, count + 1)]


def build_variant(root, master, variant):
    chapters = {name: text.replace('\\chapter', '\\section') if variant.startswith('article') else text
                for name, text in CHAPTERS.items()}
    for name, text in chapters.items():
        (master.parent / 'chapters' / (name + '.tex')).write_text(text)
    master.write_text(MASTERS[variant])
    canonical = sources(master)
    t.define(root)
    t.prepare_and_build(root)
    assert sources(master) == canonical  # preparation and builds never write the canonical master or chapters
    return {row['name']: row for row in t.view(root)['editions']}


def sources(master):
    return {path.relative_to(master.parent).as_posix(): path.read_bytes() for path in sorted(master.parent.rglob('*'))
            if path.is_file() and path.suffix in {'.tex', '.bib'} and not path.name.startswith('edition-')}


@pytest.mark.skipif(not _tools(), reason='installed TeX toolchain, pdftotext, pdfinfo and qpdf are required')
@pytest.mark.parametrize('variant', sorted(MASTERS))
def test_each_edition_opens_on_its_visible_title_with_navigation_and_no_navigation_only_page(fixture, tmp_path, variant):
    root, master = fixture
    editions = build_variant(root, master, variant)
    for name, row in editions.items():
        assert row['status'] == 'READY', row
        wrapper = (root / row['file']).read_text()
        assert wrapper.count('\\maketitle') == (0 if 'titlepage' in variant else 1)
        rendered = pages(root / row['build_target']['root'].replace('.tex', '.pdf'))
        first = rendered[0]
        assert row['title'] in first and 'Companion editions' in first, (variant, first)
        assert all(other['title'] in first for other in row['companions'])
        # Navigation never stands alone: every page that carries it also carries the edition's own title.
        assert all(row['title'] in page for page in rendered if 'Companion editions' in page)
        assert sum(row['title'] in page for page in rendered) == 1  # one opening, not a duplicate
        own = name.capitalize() + 'only'
        assert any(own in page for page in rendered) and not any(o.capitalize() + 'only' in ''.join(rendered) for o in t.NAMES if o != name)
        if variant == 'article-no-opening':
            assert own in first  # an article opens on its title block and continues on the same page
        if 'inline' in variant:  # the opening sits right after the begin token, inside the one-line title page
            assert '\\begin{titlepage}\\LaplaceEditionOpening \\centering Fixture House Imprint' in wrapper
        if 'titlepage' in variant:
            assert 'Fixture House Imprint' in first  # the master's own title page carries the edition opening
        if variant == 'book-explicit-maketitle':
            assert 'Fixture Author' in first and 'Fixture date' in first and 'Master Book Title' not in ''.join(rendered)
        targets, gotor, local = t.links_of((root / row['build_target']['root'].replace('.tex', '.pdf')).read_bytes(), tmp_path)
        assert targets == sorted(('edition-' + other['name'] + '.pdf').encode() for other in row['companions']) and gotor and not local


def test_a_wrapper_derived_by_the_previous_opening_rule_is_preparation_stale_until_prepared(fixture):
    root, master = fixture
    master.write_text(MASTERS['book-no-opening'])
    t.define(root)
    row = t.view(root, 'alpha')['editions'][0]
    prepared = t.run(root, 'build', row['prepare_action']['payload'])
    wrapper = root / prepared['file']
    current = wrapper.read_bytes()
    # The previous derivation put a free-standing companion block at body position 0 and no \maketitle.
    previous = current.replace(b'\\begin{document}\n\\maketitle\n', b'\\begin{document}\n\\begin{center}\\small Companion editions\\end{center}\n')
    assert previous != current
    wrapper.write_bytes(previous)
    assert t.view(root, 'alpha')['editions'][0]['status'] == 'PREPARATION_STALE'
    again = t.run(root, 'build', t.view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
    assert not again['unchanged'] and wrapper.read_bytes() == current and again['build_target'] == prepared['build_target']

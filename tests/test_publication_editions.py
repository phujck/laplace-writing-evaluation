"""Three named PDF editions of one synthetic three-chapter project, built by the real TeX toolchain.

One canonical source collection (master root, three chapter files, a shared preamble and
bibliography), one registry declaration, and the existing build/record/read owners. Fixture text
is synthetic public filler only.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_source, projection_viewer as compiler, storyboard
from laplace.core import checkout
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.manuscript import build_jobs, build_targets, publication_editions as editions

PROJECT = 'three'
MASTER = ('\\documentclass{article}\n\\input{preamble}\n\\title{Three Chapter Fixture}\n'
          '\\begin{document}\n\\maketitle\n\\input{chapters/alpha}\n\\input{chapters/beta}\n'
          '\\input{chapters/gamma}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n')
CHAPTERS = {
    'alpha': '\\section{Alpha}\\label{sec:alpha}\nAlphaonly marker paragraph. \\fixtureterm. See \\cite{shared2026}.\n',
    'beta': '\\section{Beta}\\label{sec:beta}\nBetaonly marker paragraph \\cite{shared2026}. Compare Section~\\ref{sec:alpha}.\n',
    'gamma': '\\section{Gamma}\\label{sec:gamma}\nGammaonly marker paragraph \\cite{shared2026}.\n',
}
PREAMBLE = '\\usepackage[hidelinks]{hyperref}\n\\newcommand{\\fixtureterm}{Shared preamble term}\n'
BIB = '@misc{shared2026,\n  title = {Shared Reference Fixture},\n  author = {Fixture, Ada},\n  year = {2026}\n}\n'
DEFINITION = [{'name': 'alpha', 'title': 'Alpha Edition', 'chapters': ['chapters/alpha']},
              {'name': 'beta', 'title': 'Beta Edition', 'chapters': ['chapters/beta']},
              {'name': 'gamma', 'title': 'Gamma Edition', 'chapters': ['chapters/gamma']}]
NAMES = ('alpha', 'beta', 'gamma')


def _tex_available():
    return bool(compiler._latexmk_bin()) and shutil.which('pdftotext') and shutil.which('qpdf')


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'workspaces'))
    for owner in (compiler, storyboard):
        monkeypatch.setattr(owner, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    code, created = writing_projects.create({'name': PROJECT, 'title': 'Three Chapter Fixture', 'kind': 'paper'}, tmp_path)
    assert code == 201, created
    master = tmp_path / manuscript_source.resolve(PROJECT, repo_root=tmp_path)['root']
    home = master.parent
    master.write_text(MASTER)
    (home / 'preamble.tex').write_text(PREAMBLE)
    (home / 'refs.bib').write_text(BIB)
    for name, text in CHAPTERS.items():
        (home / 'chapters' / (name + '.tex')).write_text(text)
    yield tmp_path, master
    shutil.rmtree(tmp_path, ignore_errors=True)


def run(root, operation, payload):
    return writing_tools.execute(root, PROJECT, 'work', operation, payload)


def http(method, url, payload=None):
    parts = urlsplit(url)
    door = compiler.handle if parts.path.startswith('/projection/') else authoring_surface.handle
    code, _, raw = door(parts.path, parse_qs(parts.query), method,
                        json.dumps(payload).encode() if payload is not None else b'')
    return code, raw


def view(root, name=None):
    value = run(root, 'document', {'target_kind': 'publication-edition'})
    return {**value, 'editions': [row for row in value['editions'] if name in (None, row['name'])]}


def states(root):
    return {row['name']: row['status'] for row in view(root)['editions']}


def define(root, value=DEFINITION):
    current = view(root)['definition']['define_action']
    return run(root, current['operation'], {**current['payload'], 'publication_editions': value})


def settle(root, target):
    until = time.monotonic() + 120
    while time.monotonic() < until:
        value = compiler.recompile_status(target['root'], repo_root=root, corpus=PROJECT, build_target=target)
        if not value['running']:
            return value
        time.sleep(.05)
    pytest.fail('edition build did not settle')


def prepare_and_build(root, names=NAMES):
    for name in names:
        row = view(root, name)['editions'][0]
        edition = run(root, row['prepare_action']['operation'], row['prepare_action']['payload'])
        assert edition['edition'] == name and edition['status'] in {'UNBUILT', 'STALE', 'READY', 'FAILED'}
        start = run(root, edition['build_action']['operation'], edition['build_action']['payload'])
        assert start['build_target'] == edition['build_target']
        assert settle(root, edition['build_target'])['ok'] is True


def pdf_of(row):
    code, raw = http('GET', row['pdf_read']['http']['url'])
    assert code == 200, raw[:300]
    assert 'sha256:' + hashlib.sha256(raw).hexdigest() == row['pdf_read']['content_revision']
    return raw


def text_of(raw, tmp):
    path = tmp / 'read.pdf'
    path.write_bytes(raw)
    return subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, text=True, check=True).stdout


def links_of(raw, tmp):
    path = tmp / 'links.pdf'
    path.write_bytes(raw)
    plain = subprocess.run(['qpdf', '--qdf', '--object-streams=disable', str(path), '-'], capture_output=True, check=True).stdout
    return sorted(set(re.findall(rb'/F \((edition-[a-z0-9-]+\.pdf)\)', plain))), b'/GoToR' in plain, b'localhost' in plain


def sources(home):
    return {path.relative_to(home).as_posix(): path.read_bytes() for path in sorted(home.rglob('*.tex')) + [home / 'refs.bib']
            if not path.name.startswith('edition-')}


@pytest.mark.skipif(not _tex_available(), reason='installed TeX toolchain, pdftotext and qpdf are required')
def test_three_named_editions_build_their_own_chapter_with_shared_references_and_companions(fixture, tmp_path):
    root, master = fixture
    home = master.parent
    before = sources(home)
    assert view(root)['status'] == 'NOT_DEFINED'
    defined = define(root)
    assert defined['publication_editions'] == DEFINITION and not defined['unchanged']
    first = view(root)
    assert first['canonical_source']['root'] == master.relative_to(root).as_posix()
    assert first['chapter_inputs'] == ['chapters/alpha', 'chapters/beta', 'chapters/gamma']
    assert states(root) == {name: 'UNPREPARED' for name in NAMES}
    # One canonical selection: wrappers never become selectable candidates.
    prepare_and_build(root)
    assert manuscript_source.resolve(PROJECT, repo_root=root)['root'] == master.relative_to(root).as_posix()
    assert not any('edition-' in row['root'] for row in manuscript_source.resolve(PROJECT, repo_root=root).get('candidates', []))
    assert not any('edition-' in row['root'] for row in writing_projects.discover(root)['candidates'])
    ready = view(root)
    identities = set()
    for row in ready['editions']:
        assert row['status'] == 'READY' and row['pdf_read']['current'], row
        identities.add((row['build_target']['root'], row['build_target']['input_revision'], row['pdf_read']['content_revision']))
        text = text_of(pdf_of(row), tmp_path)
        own = row['name'].capitalize() + 'only'
        assert own in text and row['title'] in text
        assert all(other.capitalize() + 'only' not in text for other in NAMES if other != row['name'])
        assert 'shared reference fixture' in text.lower()
        assert 'Companion editions' in text and all(c['title'] in text for c in row['companions'])
        targets, gotor, local = links_of(pdf_of(row), tmp_path)
        assert targets == sorted(('edition-' + c['name'] + '.pdf').encode() for c in row['companions']) and gotor and not local
        assert row['download_name'] == 'edition-' + row['name'] + '.pdf'
    assert len(identities) == 3
    assert 'Shared preamble term' in text_of(pdf_of(ready['editions'][0]), tmp_path)
    # Beta's reference into Alpha is qualified, not silently linked.
    beta = ready['editions'][1]
    assert [(r['label'], r['companion']) for r in beta['unsupported_references']] == [('sec:alpha', 'alpha')]
    assert not ready['editions'][0]['unsupported_references']
    assert sources(home) == before
    # Native and HTTP serve the same owner-issued targets and the same prepare action.
    code, raw = http('GET', '/authoring/document?project=' + PROJECT + '&target_kind=publication-edition')
    assert code == 200 and [r['build_target'] for r in json.loads(raw)['editions']] == [r['build_target'] for r in ready['editions']]
    code, raw = http('POST', '/authoring/build', {'project': PROJECT, **beta['prepare_action']['payload']})
    assert code == 200 and json.loads(raw)['build_target'] == beta['build_target'] and json.loads(raw)['unchanged']
    code, raw = http('GET', beta['status_read']['http']['url'])
    assert code == 200 and json.loads(raw)['build_target'] == beta['build_target'] and json.loads(raw)['fresh']


@pytest.mark.skipif(not _tex_available(), reason='installed TeX toolchain, pdftotext and qpdf are required')
def test_currentness_is_selective_by_chapter_shared_input_and_consumed_definition(fixture):
    root, master = fixture
    home = master.parent
    define(root)
    prepare_and_build(root)
    ready = {row['name']: row['build_target'] for row in view(root)['editions']}
    chapter = home / 'chapters' / 'beta.tex'
    chapter.write_text(CHAPTERS['beta'] + 'One more synthetic sentence.\n')
    assert states(root) == {'alpha': 'READY', 'beta': 'STALE', 'gamma': 'READY'}
    (home / 'refs.bib').write_text(BIB + '\n% shared change\n')
    assert states(root) == {name: 'STALE' for name in NAMES}
    (home / 'refs.bib').write_text(BIB)
    chapter.write_text(CHAPTERS['beta'])
    assert states(root) == {name: 'READY' for name in NAMES}
    (home / 'preamble.tex').write_text(PREAMBLE + '% shared preamble change\n')
    assert states(root) == {name: 'STALE' for name in NAMES}
    (home / 'preamble.tex').write_text(PREAMBLE)
    # A new master chapter no edition selects changes no edition's meaning.
    (home / 'chapters' / 'delta.tex').write_text('Deltaonly marker paragraph.\n')
    master.write_text(MASTER.replace('\\input{chapters/gamma}\n', '\\input{chapters/gamma}\n\\input{chapters/delta}\n'))
    assert {row['name']: row['build_target'] for row in view(root)['editions']} == ready
    # Changing Beta's chapters stales only Beta; renaming Beta stales its companion consumers too.
    define(root, [DEFINITION[0], {**DEFINITION[1], 'chapters': ['chapters/beta', 'chapters/delta']}, DEFINITION[2]])
    assert states(root) == {'alpha': 'READY', 'beta': 'PREPARATION_STALE', 'gamma': 'READY'}
    define(root, [DEFINITION[0], {**DEFINITION[1], 'title': 'Beta Renamed'}, DEFINITION[2]])
    assert states(root) == {name: 'PREPARATION_STALE' for name in NAMES}
    define(root)
    assert {row['name']: row['build_target'] for row in view(root)['editions']} == ready
    # A shared body line is shared meaning: every wrapper must be prepared again.
    master.write_text(MASTER.replace('\\maketitle\n', '\\maketitle\n\\noindent Shared body line.\n'))
    assert states(root) == {name: 'PREPARATION_STALE' for name in NAMES}


@pytest.mark.skipif(not _tex_available(), reason='installed TeX toolchain, pdftotext and qpdf are required')
def test_tampered_stale_wrong_project_and_wrong_edition_targets_refuse_then_recover(fixture, monkeypatch):
    root, master = fixture
    define(root)
    prepare_and_build(root, ('alpha', 'beta'))
    alpha, beta = view(root)['editions'][:2]
    target = alpha['build_target']
    monkeypatch.setattr(compiler, 'compile_tex', lambda *a, **k: pytest.fail('compiler started'))
    crossed = [{**target, 'input_revision': 'sha256:' + '0' * 64},
               {**target, 'edition': 'beta'},
               {**target, 'root': beta['build_target']['root']},
               {**target, 'project': 'other'}]
    for bad in crossed:
        with pytest.raises(build_targets.TargetRefused):
            run(root, 'build', {'build_target': bad})
        code, raw = http('POST', '/authoring/build', {'project': PROJECT, 'build_target': bad})
        assert code >= 400 and b'not served' not in raw
    # A hand-edited wrapper is not the owner's preparation.
    wrapper = root / target['root']
    wrapper.write_bytes(wrapper.read_bytes() + b'% hand edit\n')
    assert view(root, 'alpha')['editions'][0]['status'] == 'PREPARATION_STALE'
    with pytest.raises(build_targets.TargetRefused):
        run(root, 'build', {'build_target': target})
    # A stale definition guard refuses before any write.
    stale = {'prepare': {**alpha['prepare_action']['payload']['prepare'], 'definition_revision': 'sha256:' + '1' * 64}}
    with pytest.raises(build_targets.TargetRefused, match='definition changed'):
        run(root, 'build', stale)
    with pytest.raises(ValueError, match='prepare'):
        run(root, 'build', {**alpha['prepare_action']['payload'], 'build_target': target})
    # An unknown chapter refuses before the registry is written.
    registry = (root / 'registry_projects.json').read_bytes()
    with pytest.raises(ValueError, match='chapter inputs'):
        define(root, [{'name': 'alpha', 'title': 'Alpha', 'chapters': ['chapters/missing']}])
    assert (root / 'registry_projects.json').read_bytes() == registry
    # An authored file at a wrapper path is never overwritten.
    occupied = master.parent / 'edition-gamma.tex'
    occupied.write_text('Authored note, not a wrapper.\n')
    gamma = view(root, 'gamma')['editions'][0]
    with pytest.raises(build_targets.TargetRefused, match='authored file'):
        run(root, 'build', gamma['prepare_action']['payload'])
    assert occupied.read_text() == 'Authored note, not a wrapper.\n'
    # Recovery: re-read, prepare and use the newly issued target.
    monkeypatch.undo()
    for owner in (compiler, storyboard):
        monkeypatch.setattr(owner, '_repo_root', lambda: root)
    monkeypatch.setattr(checkout, 'repo_root', lambda: root)
    prepared = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
    assert prepared['build_target'] == target and not prepared['unchanged']
    run(root, 'build', {'build_target': prepared['build_target']})
    assert settle(root, prepared['build_target'])['ok'] and view(root, 'alpha')['editions'][0]['status'] == 'READY'


@pytest.mark.skipif(not _tex_available(), reason='installed TeX toolchain, pdftotext and qpdf are required')
def test_a_failed_edition_build_never_masquerades_and_leaves_siblings_ready(fixture):
    root, master = fixture
    define(root)
    prepare_and_build(root)
    saved = {row['name']: row['pdf_read'] for row in view(root)['editions']}
    output = root / saved['gamma']['build_target']['root'].removesuffix('.tex')
    output = output.with_name(output.name + '.pdf')
    saved_bytes = output.read_bytes()
    chapter = master.parent / 'chapters' / 'gamma.tex'
    chapter.write_text(CHAPTERS['gamma'] + '\\undefinedfixturemacro\n')
    gamma = view(root, 'gamma')['editions'][0]
    run(root, 'build', {'build_target': gamma['build_target']})
    assert settle(root, gamma['build_target'])['ok'] is False
    after = {row['name']: row for row in view(root)['editions']}
    # The real failed run leaves pdfTeX's partial file at the output path (existing compiler
    # semantics); the recorded receipt no longer matches, so no read is offered as current.
    assert after['gamma']['status'] == 'FAILED' and not (after['gamma'].get('pdf_read') or {}).get('current')
    assert after['gamma']['recorded_output']['content_revision'] == saved['gamma']['content_revision']
    assert not after['gamma']['recorded_output']['inputs_current']
    assert {name: after[name]['status'] for name in ('alpha', 'beta')} == {'alpha': 'READY', 'beta': 'READY'}
    assert all(after[name]['pdf_read'] == saved[name] for name in ('alpha', 'beta'))
    # The saved URL is never rebound to other bytes.
    code, raw = http('GET', saved['gamma']['http']['url'])
    if output.read_bytes() == saved_bytes:
        assert code == 200
    else:
        assert code == 409 and b'not served' in raw
    # Recovery: repair the canonical chapter and rebuild through the newly issued target.
    chapter.write_text(CHAPTERS['gamma'])
    repaired = view(root, 'gamma')['editions'][0]
    run(root, 'build', {'build_target': repaired['build_target']})
    assert settle(root, repaired['build_target'])['ok'] is True
    assert view(root, 'gamma')['editions'][0]['status'] == 'READY'


@pytest.mark.skipif(not _tex_available(), reason='installed TeX toolchain, pdftotext and qpdf are required')
def test_an_edition_build_job_cancels_through_the_existing_job_owner(fixture, monkeypatch):
    root, master = fixture
    define(root)
    prepare_and_build(root, ('alpha', 'beta'))
    alpha, beta = view(root)['editions'][:2]
    previous = (root / alpha['build_target']['root']).with_suffix('.pdf').read_bytes()
    marker = master.parent / 'fixture-edition-process.json'
    program = ("import json,os,pathlib,time\npathlib.Path('fixture-edition-process.json').write_text(json.dumps(os.getpid()))\n"
               "time.sleep(60)\n")
    original = compiler._run
    monkeypatch.setattr(compiler, '_run', lambda cmd, cwd, timeout: original([sys.executable, '-c', program], cwd, timeout))
    (master.parent / 'chapters' / 'alpha.tex').write_text(CHAPTERS['alpha'] + 'Changed before cancel.\n')
    target = view(root, 'alpha')['editions'][0]['build_target']
    start = run(root, 'build', {'build_target': target})
    until = time.monotonic() + 10
    while not marker.is_file() and time.monotonic() < until:
        time.sleep(.02)
    status = run(root, 'build_status', {'build_job': start['build_job']})
    assert status['running'] and status['build_job']['target_kind'] == 'publication-edition'
    assert run(root, 'build', status['cancel_action']['payload'])['cancel_outcome'] == 'requested'
    until = time.monotonic() + 20
    while run(root, 'build_status', {'build_job': start['build_job']})['state'] in build_jobs.ACTIVE and time.monotonic() < until:
        time.sleep(.05)
    terminal = run(root, 'build_status', {'build_job': start['build_job']})
    assert terminal['state'] == 'cancelled' and not terminal['fresh']
    assert (root / alpha['build_target']['root']).with_suffix('.pdf').read_bytes() == previous
    after = {row['name']: row for row in view(root)['editions']}
    assert after['alpha']['status'] != 'READY' and not after['alpha']['pdf_read']['current']
    assert after['beta']['status'] == 'READY' and after['beta']['pdf_read'] == beta['pdf_read']


def test_unsupported_master_layouts_refuse_and_legacy_reads_keep_their_kinds(fixture):
    root, master = fixture
    define(root)
    assert run(root, 'document', {})['selected_source']['root'] == master.relative_to(root).as_posix()
    assert run(root, 'document', {'target_kind': 'derived'})['target_kind'] == 'derived'
    master.write_text(MASTER.replace('\\input{chapters/alpha}\n', 'Lead \\input{chapters/alpha}\n'))
    result = view(root)
    assert result['status'] == 'UNAVAILABLE' and result['reason_code'] == 'UNSUPPORTED_SOURCE_LAYOUT'
    with pytest.raises(ValueError, match='alone on its line'):
        define(root, DEFINITION[:1])


def test_the_editions_card_module_is_served_beside_the_derived_output_card():
    from laplace.web import shared_ui
    code, mime, body = shared_ui.handle('/shared/publication-editions.mjs', {})
    assert code == 200 and mime.startswith('text/javascript') and b'mountPublicationEditions' in body


# -- PUB-R1a: the admitted chapter-input grammar ------------------------------------------------

@pytest.mark.parametrize('variant', ['unbraced', 'split', 'beside-text'])
def test_an_unadmitted_body_input_refuses_before_declaration_or_wrapper_effects(fixture, variant):
    root, master = fixture
    (master.parent / 'chapters' / 'other.tex').write_text('Otheronly marker paragraph.\n')
    # Positive: braced sole-line inputs and a command merely starting with "input" are admitted.
    master.write_text(MASTER.replace('\\maketitle\n', '\\maketitle\n\\newcommand{\\inputnote}{x}\n'))
    define(root)
    prepared = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
    wrapper = root / prepared['build_target']['root']
    wrapper_bytes, registry = wrapper.read_bytes(), (root / 'registry_projects.json').read_bytes()
    line = {'unbraced': '\\input chapters/other\n', 'split': '\\input\n{chapters/other}\n',
            'beside-text': 'Lead text \\input{chapters/other}\n'}[variant]
    master.write_text(MASTER.replace('\\input{chapters/gamma}\n', '\\input{chapters/gamma}\n' + line))
    result = view(root)
    assert result['status'] == 'UNAVAILABLE' and result['reason_code'] == 'UNSUPPORTED_SOURCE_LAYOUT'
    with pytest.raises(build_targets.TargetRefused, match='braced'):
        run(root, 'build', {'prepare': {'edition': 'alpha', 'definition_revision': view_definition(root, 'alpha')}})
    with pytest.raises(ValueError, match='braced'):
        define(root, DEFINITION[:2])
    assert wrapper.read_bytes() == wrapper_bytes and (root / 'registry_projects.json').read_bytes() == registry
    with pytest.raises(build_targets.TargetRefused):
        run(root, 'build', {'build_target': prepared['build_target']})


def view_definition(root, name):
    return editions.definition_revision(editions.declared(PROJECT, root), name)


# -- PUB-R1b: one build operation per request, admitted before any effect -----------------------

MIXED = [lambda job, target, prep: {'prepare': prep, 'build_job': job, 'action': 'cancel'},
         lambda job, target, prep: {'prepare': prep, 'build_target': target},
         lambda job, target, prep: {'prepare': prep, 'action': 'start'},
         lambda job, target, prep: {'prepare': None, 'build_job': job, 'action': 'cancel'},
         lambda job, target, prep: {'prepare': prep, 'build_job': None},
         lambda job, target, prep: {'build_job': job, 'build_target': target, 'action': 'cancel'}]


def test_mixed_build_selectors_refuse_in_schema_native_and_http_without_effect(fixture, monkeypatch):
    from jsonschema import Draft202012Validator
    from laplace.writing import tool_source
    from laplace.writing.schemas import SCHEMAS
    root, master = fixture
    define(root)
    prepared = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
    target, prep = prepared['build_target'], view(root, 'alpha')['editions'][0]['prepare_action']['payload']['prepare']
    job = {'schema_version': 'laplace.build-job/1', 'id': 'BLD-' + 'a' * 32, 'project': PROJECT, 'root': target['root'],
           'target_kind': 'publication-edition', 'selection_identity': target['selection_identity'],
           'input_revision': target['input_revision'], 'build_target': target}
    effects = []
    for owner, name in ((build_jobs, 'cancel'), (build_jobs, 'status'), (editions, 'prepare'), (compiler, 'recompile')):
        monkeypatch.setattr(owner, name, lambda *a, _n=name, **k: effects.append(_n) or ((200, {}) if _n == 'recompile' else {}))
    wrapper = (root / target['root']).read_bytes()
    for make in MIXED:
        payload = make(job, target, prep)
        assert list(Draft202012Validator(SCHEMAS['build']).iter_errors(payload)), payload
        with pytest.raises(ValueError):
            run(root, 'build', payload)
        with pytest.raises(build_jobs.JobRefused, match='One build operation'):
            tool_source.build(root, PROJECT, 'build', payload)
        code, raw = http('POST', '/authoring/build', {'project': PROJECT, **payload})
        assert code >= 400 and b'One build operation' in raw, raw[:200]
    code, raw = http('GET', '/authoring/build?project=three&prepare=x')
    assert code >= 400 and b'One build operation' in raw
    assert effects == [] and (root / target['root']).read_bytes() == wrapper
    # The ordinary single operations still reach their owners.
    tool_source.build(root, PROJECT, 'build', {'action': 'cancel', 'build_job': job})
    tool_source.build(root, PROJECT, 'build', {'prepare': prep})
    tool_source.build(root, PROJECT, 'build', {'build_target': target})
    assert http('POST', '/authoring/build', {'project': PROJECT, 'action': 'cancel', 'build_job': job})[0] == 200
    assert effects == ['cancel', 'prepare', 'recompile', 'cancel']


# -- PUB-R2: preparation and build admission share the compiler's per-root boundary -------------

def test_preparation_refuses_while_a_build_holds_the_compiler_boundary(fixture, monkeypatch):
    import threading
    root, master = fixture
    define(root)
    target = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])['build_target']
    entered, release = threading.Event(), threading.Event()
    def held(*args, **kwargs):
        entered.set(); release.wait(10)
        return {'ok': False, 'pdf': None, 'log_tail': 'fixture held boundary', 'outputs': None}
    monkeypatch.setattr(compiler, 'compile_tex', held)
    job = run(root, 'build', {'build_target': target})['build_job']
    assert entered.wait(10)
    try:
        define(root, [{**DEFINITION[0], 'title': 'Alpha Retitled'}, *DEFINITION[1:]])
        wrapper = (root / target['root']).read_bytes()
        with pytest.raises(build_targets.TargetRefused) as refused:
            run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
        assert refused.value.details['reason_code'] == 'BUILD_ACTIVE' and (root / target['root']).read_bytes() == wrapper
    finally:
        release.set()
    until = time.monotonic() + 20
    while run(root, 'build_status', {'build_job': job})['state'] in build_jobs.ACTIVE and time.monotonic() < until:
        time.sleep(.05)
    # Once the build has released the boundary, the same preparation publishes the changed wrapper.
    after = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])
    assert not after['unchanged'] and (root / target['root']).read_bytes() != wrapper


def test_a_build_requested_while_preparation_holds_the_boundary_starts_no_compiler(fixture, monkeypatch):
    root, master = fixture
    define(root)
    target = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])['build_target']
    started, during = [], {}
    monkeypatch.setattr(compiler, 'compile_tex', lambda *a, **k: started.append(1) or {'ok': False, 'outputs': None, 'log_tail': ''})
    original = editions.derive
    def derive(*args, **kwargs):
        if not during:  # the preparation's own derivation; the valid current target asks to build meanwhile
            during['busy'] = True
            during['reply'] = compiler.recompile(target['root'], PROJECT, 'author', repo_root=root, build_target=target)
        return original(*args, **kwargs)
    payload = view(root, 'alpha')['editions'][0]['prepare_action']['payload']
    monkeypatch.setattr(editions, 'derive', derive)
    run(root, 'build', payload)
    time.sleep(.3)
    assert during['reply'][0] == 409 and 'being prepared' in during['reply'][1]['reason'] and not started
    assert compiler._read_recompile_status(root / target['root']).get('state') != 'running'


def test_an_old_target_validated_before_a_new_preparation_cannot_start_at_the_boundary(fixture, monkeypatch):
    root, master = fixture
    define(root)
    target = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])['build_target']
    started, hooked = [], {}
    monkeypatch.setattr(compiler, 'compile_tex', lambda *a, **k: started.append(1) or {'ok': False, 'outputs': None, 'log_tail': ''})
    original = build_jobs.issue
    def issue(scope, active):
        # Between the old target's admission and its claim of the compiler boundary, preparation changes.
        if not hooked:
            hooked['done'] = True
            define(active, [{**DEFINITION[0], 'title': 'Alpha Retitled'}, *DEFINITION[1:]])
            run(active, 'build', view(active, 'alpha')['editions'][0]['prepare_action']['payload'])
        return original(scope, active)
    monkeypatch.setattr(build_jobs, 'issue', issue)
    code, reply = compiler.recompile(target['root'], PROJECT, 'author', repo_root=root, build_target=target)
    time.sleep(.3)
    assert hooked and code == 409 and reply.get('reason_code') == 'TARGET_CHANGED' and not started
    assert compiler._read_recompile_status(root / target['root']).get('build_job') is None


# -- PUB-R1b residual: a supplied target or job never falls back to the selected manuscript --------

def test_a_supplied_but_unissued_target_or_job_refuses_with_no_effect_and_issued_ones_dispatch(fixture, monkeypatch):
    from urllib.parse import parse_qs
    from laplace.web import authoring_http
    from laplace.writing import tool_source
    from laplace.native.declarations import http_lossless_query
    root, master = fixture
    define(root)
    target = run(root, 'build', view(root, 'alpha')['editions'][0]['prepare_action']['payload'])['build_target']
    effects = []
    record = lambda name, value=None: (lambda *a, **k: effects.append(name) or value)
    monkeypatch.setattr(authoring_http, '_build_selected_source', record('selected-source', {}))
    original_resolve = manuscript_source.resolve
    def resolve(*args, **kwargs):  # the native door's selected-manuscript branch is the effect boundary
        import inspect
        caller = inspect.stack()[1]
        if caller.function == 'build' and caller.filename.endswith('tool_source.py'):
            effects.append('selected-source')
            return {'status': 'unresolved'}
        return original_resolve(*args, **kwargs)
    monkeypatch.setattr(manuscript_source, 'resolve', resolve)
    monkeypatch.setattr(compiler, 'recompile', lambda root_, project, by, **k: effects.append(('recompile', k.get('build_target'))) or (200, {}))
    monkeypatch.setattr(compiler, 'recompile_status', lambda root_, **k: effects.append(('status', k.get('build_target'))) or {})
    for owner, name in ((build_jobs, 'cancel'), (build_jobs, 'status'), (editions, 'prepare')):
        monkeypatch.setattr(owner, name, record(name, {}))
    # The reviewer's exact request, then the same rule over a small malformed-presence family.
    code, raw = http('POST', '/authoring/build', {'project': PROJECT, 'build_target': ''})
    assert code >= 400 and effects == [], (code, raw[:200], effects)
    bodies = [{'build_target': value} for value in ('', None, '{}', json.dumps(target), {}, [], 0, {'kind': 'publication-edition'})]
    bodies += [{'action': 'cancel', 'build_job': value} for value in ('', None, {}, 'x')]
    for body in bodies:
        assert http('POST', '/authoring/build', {'project': PROJECT, **body})[0] >= 400, body
        with pytest.raises(ValueError):
            tool_source.build(root, PROJECT, 'build', body)
        with pytest.raises(ValueError):
            run(root, 'build', body)
    assert http_lossless_query('/authoring/build', 'GET')
    for query in ('build_target=', 'build_target=null', 'build_target=%7B%7D', 'build_job=', 'build_target=x'):
        parsed = parse_qs('project=three&' + query, keep_blank_values=True)
        assert authoring_surface.handle('/authoring/build', parsed, 'GET', b'')[0] >= 400, query
        with pytest.raises(ValueError):
            tool_source.build(root, PROJECT, 'build_status', {key: value[0] for key, value in parsed.items() if key != 'project'})
    assert effects == []
    # Issued selectors dispatch to their owners; only a request with no selector is the selected manuscript.
    assert http('POST', '/authoring/build', {'project': PROJECT, 'build_target': target})[0] == 200
    code, _ = http('GET', '/authoring/build?' + urlencode({'project': PROJECT, 'build_target': json.dumps(target)}))
    assert code == 200 and effects == [('recompile', target), ('status', target)]
    tool_source.build(root, PROJECT, 'build', {'build_target': target})
    assert effects[-1] == ('recompile', target)
    effects.clear()
    assert http('POST', '/authoring/build', {'project': PROJECT})[0] == 200
    with pytest.raises(ValueError, match='Select a manuscript source'):
        tool_source.build(root, PROJECT, 'build', {})
    assert effects == ['selected-source', 'selected-source']

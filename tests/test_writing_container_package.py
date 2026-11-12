import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("writing_container_package", Path(__file__).parents[1] / "scripts/writing_container_package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def fixture(tmp_path):
    parts = package.Parts(tmp_path, limit=17)
    content = bytes(range(256)) * 16
    with gzip.GzipFile(fileobj=parts, mode="wb", mtime=0) as stream:
        stream.write(content)
    parts.close()
    data = {"schema": package.SCHEMA, "platform": "linux/amd64",
            "image_id": "sha256:" + "a" * 64,
            "local_tag": "laplace-writing:fixture", "parts": parts.rows}
    (tmp_path / package.MANIFEST).write_text(json.dumps(data), encoding="utf-8")
    return data, content


def test_split_stream_round_trips_in_order_without_reassembly_file(tmp_path):
    manifest, content = fixture(tmp_path)
    assert len(manifest["parts"]) > 1
    assert package.verified_package(tmp_path) == manifest
    raw = b"".join((tmp_path / x["name"]).read_bytes() for x in manifest["parts"])
    assert gzip.decompress(raw) == content


@pytest.mark.parametrize("change", ["corrupt", "missing", "reorder", "escape", "image", "tag"])
def test_bad_package_refused_before_docker(tmp_path, monkeypatch, change):
    manifest, _ = fixture(tmp_path)
    first = tmp_path / manifest["parts"][0]["name"]
    if change == "corrupt":
        raw = first.read_bytes(); first.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    elif change == "missing":
        first.unlink()
    elif change == "reorder":
        manifest["parts"].reverse()
    elif change == "escape":
        manifest["parts"][0]["name"] = "../outside"
    elif change == "image":
        manifest["image_id"] = "sha256:bad"
    else:
        manifest["local_tag"] = "some-other-image:latest"
    (tmp_path / package.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(package, "inspect_image", lambda *_: pytest.fail("Docker must not run before verification"))
    with pytest.raises(ValueError):
        package.load(tmp_path)


def test_existing_image_must_match_recorded_id_and_platform(tmp_path, monkeypatch):
    manifest, _ = fixture(tmp_path)
    monkeypatch.setattr(package, "inspect_image", lambda *_: {"Id": manifest["image_id"], "Os": "linux", "Architecture": "arm64"})
    with pytest.raises(ValueError, match="recorded identity"):
        package.load(tmp_path)


# ---- the build-input closure (container input closure, 2026-10-20) --------------------------------------------------
# The two Docker build contexts are allowlists (`**` denies everything, `!pattern` re-admits). What the image runs
# (the declared evaluator suite in docs/writing-pytest.ini) and what the exported tooling imports (the exporter and
# verifier's sibling scripts) must be admitted; project material, history, private and credential paths must stay
# denied. Evaluated with Docker's own rule: patterns in order, the last match decides, `**` spans path segments.
REPO = Path(__file__).parents[1]
IGNORE_FILES = ('deploy/writing/Dockerfile.dockerignore', 'deploy/writing/Dockerfile.refresh.dockerignore')
REQUIRED_CONTEXT = (
    'pyproject.toml', 'README.md', 'src/laplace/web/writing_server.py', 'docs/writing-pytest.ini', 'docs/writing-reviewer-guide.md',
    'scripts/export_writing_evaluation.py', 'scripts/verify_writing_evaluation.py', 'scripts/writing_eval_manifest.py',
    'scripts/writing_export_bytes.py', 'scripts/writing_portable_links.py', 'scripts/inspect_writing_export.py', 'scripts/writing_container_package.py',
    'tests/project_landing.test.mjs', 'tests/helpers/evidence_reader_harness.mjs', 'deploy/writing/writing-entrypoint.sh', 'deploy/writing/smoke.py',
)
DENIED_CONTEXT = (
    'registry_projects.json', 'contract/talk.jsonl', 'contract/journal.jsonl', 'corpus_friction/work_orders.jsonl',
    'writing_projects/alpha/manuscript/main.tex', 'synthetics papers/book/manuscript/main.tex', 'evidence/notes.md',
    '.env', '.auth/token', '.credentials/x', '.laplace-state/x', 'private/notes.txt', 'soul/x.md', '.claude/settings.json',
    'tests/test_author_history.py', 'scripts/wake.py',
)


def _pattern_regex(pattern):
    import re
    out = []
    for i, segment in enumerate(pattern.split('/')):
        if segment == '**':
            out.append('(?:[^/]+(?:/[^/]+)*)?' if i == len(pattern.split('/')) - 1 else '(?:[^/]+/)*')
            continue
        piece = ''.join('[^/]*' if ch == '*' else '[^/]' if ch == '?' else re.escape(ch) for ch in segment)
        out.append(piece + ('/' if i < len(pattern.split('/')) - 1 else ''))
    return re.compile('^' + ''.join(out).replace('/(?:[^/]+/)*', '/(?:[^/]+/)*').rstrip('/') + '$')


def context_admits(rules, relative):
    """Docker's .dockerignore decision for one path: the last matching rule wins; nothing matching means admitted."""
    admitted = True
    for rule in rules:
        rule = rule.strip()
        if not rule or rule.startswith('#'):
            continue
        negate = rule.startswith('!')
        pattern = rule[1:] if negate else rule
        regex = _pattern_regex(pattern)
        if regex.match(relative) or (pattern.endswith('/**') and relative.startswith(pattern[:-3] + '/')) or pattern == '**':
            admitted = negate
    return admitted


def test_both_build_contexts_admit_the_evaluator_suite_and_tooling_closure_and_deny_project_history_and_private_inputs():
    declared = [line.split('=', 1)[1].split() for line in (REPO / 'docs/writing-pytest.ini').read_text().splitlines() if line.startswith('python_files')][0]
    assert 'test_writing_portable_core.py' in declared
    contexts = {name: (REPO / name).read_text().splitlines() for name in IGNORE_FILES}
    assert contexts[IGNORE_FILES[0]] == contexts[IGNORE_FILES[1]], 'the full and refresh build contexts admit the same closure'
    for name, rules in contexts.items():
        for test in declared:
            assert context_admits(rules, 'tests/' + test), (name, test)
            assert (REPO / 'tests' / test).is_file(), test
        for required in REQUIRED_CONTEXT:
            assert context_admits(rules, required), (name, required)
            assert (REPO / required).exists() or required == 'README.md', required   # README.md is generated into the exported checkout the image is built from
        for denied in DENIED_CONTEXT:
            assert not context_admits(rules, denied), (name, denied)
    # the exporter and verifier import their siblings by name from their own directory: every one of them is admitted
    siblings = {'writing_eval_manifest', 'writing_export_bytes', 'writing_portable_links'}
    for script in ('scripts/export_writing_evaluation.py', 'scripts/verify_writing_evaluation.py', 'scripts/writing_eval_manifest.py'):
        text = (REPO / script).read_text()
        for name in siblings:
            if name in text:
                assert all(context_admits(rules, 'scripts/%s.py' % name) for rules in contexts.values()), (script, name)

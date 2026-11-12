"""The writing recipe's cache boundary (M5 S3), read from the recipe text; no image is built.

Every named target (runtime, provider-codex, provider-claude, provider-both) is its dependency chain followed by
one APP block. The chain holds the OS packages, the Python dependency closure from the two pyproject files and,
for providers, Node and the pinned provider CLIs; it never copies application source. So a source-only change
rebuilds only the APP layers and never the heavy dependency or provider npm layers. The four APP blocks are
byte-identical, so the targets cannot drift apart.
"""
import re
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1] / 'deploy' / 'writing' / 'Dockerfile'
TARGETS = ('runtime', 'provider-codex', 'provider-claude', 'provider-both')
SOURCE_COPIES = ('COPY src ', 'COPY README.md ', 'COPY atlas/README.md ', 'COPY deploy/writing/')


def _stages(text):
    """[(name, base, instructions)] with continuation lines joined and comments dropped."""
    stages, logical, pending = [], [], ''
    heredoc = None
    for raw in text.splitlines():
        if heredoc is not None:
            logical[-1] += '\n' + raw
            if raw.strip() == heredoc:
                heredoc = None
            continue
        line = raw.rstrip()
        if not pending and (not line.strip() or line.lstrip().startswith('#')):
            continue
        pending += line[:-1] + ' ' if line.endswith('\\') else line
        if line.endswith('\\'):
            continue
        logical.append(pending.strip())
        if '<<' in pending:
            heredoc = pending.split('<<', 1)[1].strip().strip("'\"")
        pending = ''
    for instruction in logical:
        if instruction.startswith('FROM '):
            parts = instruction.split()
            stages.append((parts[3] if len(parts) > 3 else parts[1], parts[1], []))
        elif stages:
            stages[-1][2].append(instruction)
    return stages


def _chain(stages, name):
    by_name = {stage[0]: stage for stage in stages}
    chain = []
    while name in by_name:
        chain.insert(0, by_name[name])
        name = by_name[name][1]
    return chain


def _app(instructions):
    return [line for line in instructions if not line.startswith('LABEL ')]


def test_every_named_target_is_a_source_free_dependency_chain_then_one_identical_app_block():
    stages = _stages(RECIPE.read_text(encoding='utf-8'))
    names = [stage[0] for stage in stages]
    assert all(target in names for target in TARGETS), names
    apps = []
    for target in TARGETS:
        chain = _chain(stages, target)
        *dependencies, own = chain
        assert dependencies, target + ' builds on a dependency chain'
        for stage in dependencies:
            copied = [line for line in stage[2] if line.startswith(SOURCE_COPIES)]
            assert copied == [], f'{target}: dependency stage {stage[0]} copies application source {copied}'
        app = _app(own[2])
        assert any(line.startswith('COPY src ') for line in app) and 'USER laplace' in app and app[-1] == 'WORKDIR /workspace'
        apps.append(app)
    assert all(app == apps[0] for app in apps), 'the four APP blocks are byte-identical'


def test_provider_clis_and_python_dependencies_install_before_any_source_and_keep_their_pins():
    stages = _stages(RECIPE.read_text(encoding='utf-8'))
    for target, specs in (('provider-codex', ['@openai/codex@0.160.1']), ('provider-claude', ['@anthropic-ai/claude-code@2.1.304']),
                          ('provider-both', ['@openai/codex@0.160.1', '@anthropic-ai/claude-code@2.1.304'])):
        *dependencies, own = _chain(stages, target)
        installs = [line for stage in dependencies for line in stage[2] if 'npm install --global' in line]
        assert len(installs) == 1 and not any('npm install' in line for line in own[2]), target
        args = ' '.join(line for stage in dependencies for line in stage[2] if line.startswith('ARG '))
        assert all(spec in args for spec in specs), target
    deps = _chain(stages, 'runtime')[0]
    copies = [line for line in deps[2] if line.startswith('COPY ')]
    assert copies == ['COPY atlas/pyproject.toml ./atlas/', 'COPY pyproject.toml ./'], 'only the dependency declarations precede the closure install'
    assert any('pip", "install", "--no-cache-dir"' in line for line in deps[2])


def test_runtime_image_configuration_is_kept_for_every_target():
    stages = _stages(RECIPE.read_text(encoding='utf-8'))
    for target in TARGETS:
        everything = [line for stage in _chain(stages, target) for line in stage[2]]
        assert 'EXPOSE 8771' in everything
        assert 'ENTRYPOINT ["/usr/bin/tini","--","/usr/local/bin/laplace-writing-entrypoint"]' in everything
        assert any(line.startswith('HEALTHCHECK ') for line in everything)
        assert [line for line in everything if line.startswith('USER ')][-1] == 'USER laplace'


REFRESH = Path(__file__).resolve().parents[1] / 'deploy' / 'writing' / 'Dockerfile.refresh'


def test_refresh_from_a_pre_r2_image_retires_the_old_atlas_source_tree_and_leaves_one_source_copy(tmp_path):
    """RR-R1 (2026-10-20): the refresh recipe is replayed over a synthetic OLD image layout (an image built before
    the Atlas source moved to src/atlas): the retired /opt/laplace/atlas/src must be removed by the recipe's own
    retirement step, the new source copied by its own COPY lines, and nothing else may put a second Atlas source
    tree in the image. The paths come from the recipe text; no image is built."""
    import shutil
    stages = _stages(REFRESH.read_text(encoding='utf-8'))
    assert len(stages) == 1
    instructions = stages[0][2]
    retirement = next(line for line in instructions if line.startswith('RUN ') and 'rm -rf' in line)
    removed = retirement.split('rm -rf', 1)[1].split('&&')[0].split()
    assert '/opt/laplace/atlas/src' in removed and '/opt/laplace/src' in removed, removed
    assert not any(line.startswith('COPY atlas/src') for line in instructions), 'no second Atlas source copy'
    copies = [line.split()[1:] for line in instructions if line.startswith('COPY ')]
    assert ['src', './src'] in copies and ['atlas/pyproject.toml', './atlas/'] in copies
    # the synthetic old image: both source copies of the pre-R2 layout and both installed packages
    image = tmp_path / 'image'
    for rel in ('opt/laplace/atlas/src/atlas/store.py', 'opt/laplace/atlas/src/atlas/__init__.py', 'opt/laplace/src/laplace/__init__.py',
                'opt/laplace/src/laplace/representation/atlas_bridge.py', 'usr/local/lib/python3.12/site-packages/atlas/__init__.py',
                'usr/local/lib/python3.12/site-packages/laplace/__init__.py', 'opt/laplace/atlas/README.md', 'opt/laplace/atlas/pyproject.toml'):
        (image / rel).parent.mkdir(parents=True, exist_ok=True); (image / rel).write_text('old\n')
    # the new source tree the recipe copies from (one home: src/atlas beside src/laplace)
    context = tmp_path / 'context'
    for rel in ('src/atlas/__init__.py', 'src/atlas/store.py', 'src/laplace/__init__.py', 'src/laplace/representation/writing_representation.py', 'atlas/pyproject.toml', 'atlas/README.md'):
        (context / rel).parent.mkdir(parents=True, exist_ok=True); (context / rel).write_text('new\n')
    # replay the retirement step, then the source COPY lines, exactly as written
    for path in removed:
        shutil.rmtree(image / path.lstrip('/'), ignore_errors=True)
    for source, destination in copies:
        if source.startswith(('deploy/', 'docs/', 'tests/', 'scripts/', 'profiles', 'README.md', 'pyproject.toml')):
            continue
        target = image / 'opt/laplace' / destination.removeprefix('./')
        if (context / source).is_dir():
            shutil.copytree(context / source, target, dirs_exist_ok=True)
        elif (context / source).is_file():
            target.mkdir(parents=True, exist_ok=True); shutil.copy2(context / source, target / Path(source).name)
    assert not (image / 'opt/laplace/atlas/src').exists(), 'the retired Atlas source location survived the refresh'
    assert (image / 'opt/laplace/src/atlas/store.py').read_text() == 'new\n'
    assert (image / 'opt/laplace/src/laplace/representation/writing_representation.py').read_text() == 'new\n'
    assert not (image / 'usr/local/lib/python3.12/site-packages/atlas').exists()
    atlas_trees = sorted(str(p.relative_to(image)) for p in image.rglob('__init__.py') if p.parent.name == 'atlas')
    assert atlas_trees == ['opt/laplace/src/atlas/__init__.py'], atlas_trees
    assert (image / 'opt/laplace/atlas/pyproject.toml').read_text() == 'new\n', 'the distribution metadata is refreshed, not the retired source'


def _font_audit(text: str) -> tuple[list[str], str]:
    """The recipe's TeX input audit loop, verbatim: its input list and the loop as one shell command."""
    import re
    joined = text.replace('\\\n', ' ')
    match = re.search(r'for input in ([^;]+); do\s+(kpsewhich .*?;)\s+done', joined)
    assert match, 'the recipe carries no kpsewhich input audit'
    return match.group(1).split(), match.group(0)


@pytest.mark.parametrize('recipe', ['Dockerfile', 'Dockerfile.refresh'])
def test_the_font_audit_names_the_shipped_t1_map_and_outline_and_refuses_a_missing_input(recipe, tmp_path):
    """R5 font audit (2026-10-21): Debian's cm-super 0.3.4 ships cm-super-minimal-t1.map (package cm-super-minimal, which
    cm-super depends on) and sfrm1000.pfb; there is no cm-super-t1.map, so auditing that name refused a correct image.
    Both profiles install cm-super and audit the shipped T1 map and an EC outline; the loop, replayed as written against a
    kpsewhich that knows a given set of inputs, passes when all are present and refuses, naming the input, when one is not."""
    import subprocess
    text = (Path(__file__).resolve().parents[1] / 'deploy' / 'writing' / recipe).read_text(encoding='utf-8')
    assert re.search(r'apt-get install[^&]*\bcm-super\b', text.replace('\\\n', ' ')), 'the profile installs cm-super'
    inputs, loop = _font_audit(text)
    assert {'cm-super-minimal-t1.map', 'sfrm1000.pfb'} <= set(inputs) and 'cm-super-t1.map' not in inputs
    def replay(known):
        bindir = tmp_path / ('bin-%d' % len(known)); bindir.mkdir()
        (bindir / 'kpsewhich').write_text('#!/bin/sh\ncase " %s " in *" $1 "*) echo /found/$1;; *) exit 1;; esac\n' % ' '.join(known))
        (bindir / 'kpsewhich').chmod(0o755)
        return subprocess.run(['sh', '-c', loop], capture_output=True, text=True, env={'PATH': '%s:/usr/bin:/bin' % bindir})
    complete = replay(inputs)
    assert complete.returncode == 0, complete.stderr
    without_map = replay([name for name in inputs if name != 'cm-super-minimal-t1.map'])
    assert without_map.returncode == 1 and 'missing TeX distribution input: cm-super-minimal-t1.map' in without_map.stderr

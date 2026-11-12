"""Initialize one owned volume; start the installed application without host state."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

SEED = Path('/opt/evaluation/seed')
DATA = Path('/data')
WORKSPACE = DATA / 'workspace'
MARKER = DATA / 'evaluation-workspace.json'
REVISION = Path('/opt/evaluation/source-revision').read_text().strip()


def initialise():
    DATA.mkdir(parents=True, exist_ok=True)
    if MARKER.exists():
        saved = json.loads(MARKER.read_text())
        if saved.get('source_revision') != REVISION:
            raise SystemExit('This volume belongs to another evaluation edition. Keep it for your work; use a new named volume for this image.')
        if not (WORKSPACE / 'registry_projects.json').is_file():
            raise SystemExit('The initialized workspace is incomplete. Restore its backup or use a new named volume.')
        return
    if any(DATA.iterdir()):
        raise SystemExit('Refusing to overwrite an unrecognized nonempty /data volume. Use an empty named volume.')
    staging = DATA / 'workspace.initializing'
    try:
        shutil.copytree(SEED, staging)
        subprocess.run([sys.executable, str(staging / 'scripts/check_evaluation_selection.py')], cwd=staging, check=True)
        original_runtime = hashlib.sha256((staging / 'runtime_profiles.toml').read_bytes()).hexdigest()
        subprocess.run([sys.executable, str(staging / 'scripts/configure_writing_runtime.py'),
                        '--root', str(staging), '--python', sys.executable, '--replace'], check=True)
        # This is a real Git-backed source snapshot of the distributed files.
        # Its image/source provenance remains the explicit upstream revision.
        subprocess.run(['git', 'init', '-q', '-b', 'master', str(staging)], check=True)
        (staging / '.git/info/exclude').write_text('.laplace-state/\n.laplace-cache/\n')
        subprocess.run(['git', '-C', str(staging), 'add', '-f', '.'], check=True)
        subprocess.run(['git', '-C', str(staging), '-c', 'user.name=Evaluation workspace',
                        '-c', 'user.email=evaluation@localhost', 'commit', '-q', '-m',
                        'Initialize distributed evaluation ' + REVISION], check=True)
        staging.rename(WORKSPACE)
        saved = {'schema': 'eigen.container-workspace/1', 'source_revision': REVISION,
                 'seed_manifest_sha256': hashlib.sha256((SEED / 'release/selection-manifest.json').read_bytes()).hexdigest(),
                 'runtime_setup': {'source_sha256': original_runtime,
                                   'configured_sha256': hashlib.sha256((WORKSPACE / 'runtime_profiles.toml').read_bytes()).hexdigest(),
                                   'python': sys.executable}, 'providers_started': 0}
        MARKER.write_text(json.dumps(saved, indent=2) + '\n')
    except BaseException:
        # A failed initialization is retained for diagnosis; never replace data.
        raise


def main():
    initialise()
    for path in [Path(os.environ['HOME']), DATA / 'session-workspaces']:
        path.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE)
    if len(sys.argv) > 1:
        os.execvp(sys.argv[1], sys.argv[1:])
    args = [sys.executable, '-m', 'laplace.web.writing_server', '--root', str(WORKSPACE),
            '--state', str(WORKSPACE / '.laplace-state'), '--session-workspaces',
            str(DATA / 'session-workspaces'), '--host', '0.0.0.0', '--port', '8771']
    os.execv(sys.executable, args)


if __name__ == '__main__':
    main()

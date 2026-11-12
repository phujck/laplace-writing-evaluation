"""Run the retained fixture under a small parent for reproducible RSS accounting.

On Linux ru_maxrss can include a high-water mark inherited before exec. A small
launcher gives the unchanged producer a fresh child whose initial resident set
belongs to this image. Its original memory/CPU guards and measurements remain
in force. Arguments are passed verbatim without a shell.
"""
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    producer = root / 'writing_projects/memory-in-pieces/evidence/DYNAMIC_MEMORY_DEMO_2026-11-11/incremental_demo_checked.py'
    if not producer.is_file():
        raise SystemExit('The declared Dynamic Memory producer is missing: ' + str(producer))
    return subprocess.run([sys.executable, str(producer), *sys.argv[1:]], check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())

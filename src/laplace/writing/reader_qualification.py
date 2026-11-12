"""Explicit local operator commission through existing reader admission/execution.

This entry neither installs nor awards qualification. Importing it is passive.
There is no HTTP/native/SDK selector for this trusted local action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def commission(root, value):
    from laplace.writing import turn_admission,turn_jobs,session_reads,turn_control
    root=Path(root).resolve()
    acknowledgement=turn_admission.start_reader_qualification(root,value)
    job=turn_jobs._JOBS.get(acknowledgement['turn_id'])
    if job is not None:
        try:
            with job['condition']:
                while not job['done']:job['condition'].wait(timeout=.2)
        except BaseException:
            turn_control.interrupt_turn(root,{'project':value['project'],'turn_id':acknowledgement['turn_id']})
            with job['condition']:
                while not job['done']:job['condition'].wait(timeout=.2)
            raise
    exact=session_reads.session_turn_detail(root,value['project'],acknowledgement['turn_id'],'turn')
    return {'purpose':'operator-qualification','admission':acknowledgement,'result':exact,
        'qualification_installed':False,'judgement':'Operator attempt only; Root must judge retained canary evidence separately.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--commission',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(commission(args.root,json.loads(args.commission.read_text())),ensure_ascii=False))


if __name__=='__main__':main()

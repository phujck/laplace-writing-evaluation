"""THE LIVE TURN REGISTRY (S1 B2): the one in-process owner of accepted-but-unfinished writing work.

Owns exactly these process-lifetime objects, each with its own lock; authoring_surface keeps the old
names as aliases of the SAME objects (`authoring_surface._JOBS is turn_jobs._JOBS`):

  _JOBS                      turn id -> live job (events, condition, text, provider, done); written by
                             writing.turn_execution, read by streams, interrupts and proposal readers.
                             Completed jobs are evicted by turn_execution (the newest 8 stay readable).
  _STARTING_TURNS (+ lock)   accepted turn starts before their job exists (context construction).
  _ACTIVE_HTTP_MUTATIONS (+ lock)  owner writes in flight, shared with the launcher's update/stop drain.

Readers: active_turn_count / active_work_projection (service lifecycle and close/recovery decisions),
work_activity (one project's Work-targeted live execution, read by project_work_activity) and
http_mutation (the scoped owner-write marker). Nothing here is persisted; a restart forgets it, and
remote child turns are observed through writing.child_hosts.
"""
from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from laplace.writing.records._fold import _LOCK


_JOBS: dict[str, dict] = {}
#: True only inside the one-shot door host a dispatched child's turn runs in (writing_tools.main --start-child-turn),
#: so that start_turn there runs the turn instead of detaching it again. A process fact: nothing persists it. Read with
#: child_host(), set with set_child_host(); the hermetic replay sets it to keep the whole chain in one process.
_CHILD_HOST = False


def child_host() -> bool:
    return _CHILD_HOST


def set_child_host(value: bool) -> None:
    global _CHILD_HOST
    _CHILD_HOST = bool(value)
_STARTING_TURNS: dict[str, dict] = {}
_STARTING_TURNS_LOCK = threading.Lock()
_ACTIVE_HTTP_MUTATIONS: dict[str, dict] = {}
_ACTIVE_HTTP_MUTATIONS_LOCK = threading.Lock()


def active_turn_count() -> int:
    """Count accepted turn starts through provider completion.

    Context construction precedes creation of the durable turn/job.  Keep that
    bounded request interval visible to the service lifecycle so a source update
    cannot retire the writer between accepting POST /authoring/turn and publishing
    its job identity.
    """
    with _STARTING_TURNS_LOCK:
        starting = len(_STARTING_TURNS)
    local = {job["id"] for job in _JOBS.values() if not job["done"]}
    from laplace.writing import child_hosts  # the remote-host observation; lazy so the registry stays a leaf
    remote = {row.get("turn_id") or row.get("session_id") for row in child_hosts.active_child_hosts()}
    return starting + len(local | remote)


def active_work_projection(active_runs=(), limit: int = 16) -> tuple[list[dict], int]:
    """Bounded in-memory identities for a close/recovery decision."""
    with _STARTING_TURNS_LOCK:
        starting = [dict(row) for row in _STARTING_TURNS.values()]
    with _ACTIVE_HTTP_MUTATIONS_LOCK:
        mutations = [dict(row) for row in _ACTIVE_HTTP_MUTATIONS.values()]
    rows = [{"kind":"turn-start", "project":row.get("project"),
             "session_id":row.get("session_id"), "turn_id":None, "work_id":row.get("work_id"),
             "label":row.get("label"), "provider":row.get("provider")}
            for row in starting]
    rows.extend({"kind":"turn", "project":job.get("project"),
                 "session_id":job.get("session_id"), "turn_id":job.get("id"), "work_id":job.get("work_id"),
                 "label":job.get("request_label"), "provider":job.get("provider_name")}
                for job in _JOBS.values() if not job.get("done"))
    local_ids = {row.get("turn_id") for row in rows}
    from laplace.writing import child_hosts  # the remote-host observation; lazy so the registry stays a leaf
    rows.extend({"kind":"turn", "project":row.get("project"),
                 "session_id":row.get("session_id"), "turn_id":row.get("turn_id"), "work_id":row.get("work_id"),
                 "label":row.get("packet"), "provider":row.get("provider")}
                for row in child_hosts.active_child_hosts() if row.get("turn_id") not in local_ids)
    rows.extend({"kind":"research-run", "project":run.get("project"),
                 "session_id":None, "turn_id":None, "run_id":run.get("id"),
                 "label":"Research run " + str(run.get("id") or ""), "provider":None,
                 "state":run.get("state"), "cleanup":run.get("cleanup"),
                 "reason":run.get("reason"), "job_path":run.get("job_path")}
                for run in active_runs)
    rows.extend({"kind":"http-mutation","project":row.get("project"),
                 "session_id":None,"turn_id":None,"path":row.get("path"),
                 "label":"Saving " + str(row.get("path") or "project update"),"provider":None}
                for row in mutations)
    rows.sort(key=lambda row:(str(row.get("project") or ""),str(row.get("turn_id") or row.get("run_id") or "")))
    return rows[:limit], max(0,len(rows)-limit)


def work_activity(project: str, root: Path | None = None, limit: int = 32) -> dict:
    """Bounded live in-app execution of ONE project that names a Work (project_work_activity reads it).

    The same three owners as active_work_projection, filtered to the project before the bound: accepted
    turn starts (STARTING), live turns of this process (RUNNING) and child-host records (their own
    STARTING/WAITING/RUNNING/ORPHANED state). ``omitted`` counts Work-targeted rows past the bound and
    ``untargeted`` the live rows that name no Work; neither is inferred into a Work's activity."""
    with _STARTING_TURNS_LOCK:
        rows = [{"kind":"turn-start", "work_id":row.get("work_id"), "session_id":row.get("session_id"),
                 "turn_id":None, "state":"STARTING"}
                for row in _STARTING_TURNS.values() if row.get("project") == project]
    rows.extend({"kind":"turn", "work_id":job.get("work_id"), "session_id":job.get("session_id"),
                 "turn_id":job.get("id"), "state":"RUNNING"}
                for job in list(_JOBS.values()) if not job.get("done") and job.get("project") == project)
    local_ids = {row["turn_id"] for row in rows if row["turn_id"]}
    from laplace.writing import child_hosts  # the remote-host observation; lazy so the registry stays a leaf
    rows.extend({"kind":"child-host", "work_id":row.get("work_id"), "session_id":row.get("session_id"),
                 "turn_id":row.get("turn_id"), "state":row.get("state"),
                 **({"dispatch_id":row["dispatch_id"]} if row.get("dispatch_id") else {})}
                for row in child_hosts.active_child_hosts(root)
                if row.get("project") == project and row.get("turn_id") not in local_ids)
    targeted = [row for row in rows if isinstance(row.get("work_id"), str) and row["work_id"]]
    targeted.sort(key=lambda row:(row["work_id"], str(row.get("turn_id") or row.get("session_id") or "")))
    return {"rows":targeted[:limit], "omitted":max(0,len(targeted)-limit), "untargeted":len(rows)-len(targeted)}


@contextmanager
def http_mutation(path: str, project: str = ""):
    """Expose owner writes and share the launcher's update/stop drain lock."""
    token=uuid.uuid4().hex
    lock_handle=None
    try:
        state=os.environ.get("LAPLACE_WRITING_STATE")
        if state:
            import fcntl
            lock_path=Path(state).with_suffix(Path(state).suffix+".lock")
            lock_path.parent.mkdir(parents=True,exist_ok=True)
            lock_handle=lock_path.open("a+",encoding="utf-8")
            fcntl.flock(lock_handle.fileno(),fcntl.LOCK_SH)
        with _ACTIVE_HTTP_MUTATIONS_LOCK:
            _ACTIVE_HTTP_MUTATIONS[token]={"path":str(path),"project":str(project or "")}
        try:yield
        finally:
            with _ACTIVE_HTTP_MUTATIONS_LOCK:
                _ACTIVE_HTTP_MUTATIONS.pop(token,None)
    finally:
        if lock_handle is not None:
            try:
                import fcntl
                fcntl.flock(lock_handle.fileno(),fcntl.LOCK_UN)
            finally:lock_handle.close()


def evict_finished(keep: int = 8) -> None:
    """Completed transcripts live in the journal, not indefinitely in RAM: keep the newest `keep` done jobs
    (under the journal fold lock, as before the move)."""
    with _LOCK:
        finished = [key for key, job in _JOBS.items() if job["done"]]
        for key in finished[:-keep]:
            _JOBS.pop(key, None)



"""Fixture callers explicitly consume the owner's current work guards before acting."""
from laplace.work import project_work

def standing_payload(project,payload,root):
 rows=project_work._tasks(project,root);row=rows[payload['id']]
 basis,_=project_work._work_basis(rows,row['id'])
 return {'expected_work_scope_revision':basis['scope_revision'],
         'expected_work_status_revision':project_work._standing_revision(row),
         'expected_dependency_revision':project_work._dependency_revision(row,rows),**payload}

def guarded_transition(project,payload,root,**kwargs):
 return project_work.transition(project,standing_payload(project,payload,root),root,**kwargs)

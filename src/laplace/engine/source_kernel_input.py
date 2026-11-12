"""Selected declared Source leaves over existing keeper/fold custody; no publisher or store."""
import copy
from pathlib import Path
from laplace.core.identity import canonical_digest

CARRY_SCHEMA='laplace.source-close-carry/1'


def coverage_inputs(root):
 """Active publication owns new selections; verified historical coverage remains historical."""
 from laplace.representation import source_publication
 active=source_publication.selections(root)
 if active is not None:return active
 from laplace.representation import semantic_vertical as V
 if not (Path(root)/V.COVERAGE_PATH).is_file():return []
 value=V.load_coverage(root)
 return value.get('source_kernel_inputs',[])


def close_inputs(root,packet,parent):
 """The ordinary close's one validation of the active packet against its parent's retained leaves.

 work.source_kernel gives every row a state (CURRENT, CARRIED, STALE, UNKNOWN); none of them
 refuses the close. Integrity refusals (custody, bodies, retained values, packet rows) still raise.
 The result carries the packet, the parent's leaves for its rows and the per-row currentness to
 the ordinary publisher, which records them in its receipt.
 """
 from laplace.work import source_kernel
 from laplace.work.owner_discovery import owned_workspace
 normalized=source_kernel._packet(packet,retained=True);selected=(parent or {}).get('selected_content') or {}
 missing=sorted({row['node_id'] for row in normalized['inputs']}-set(selected))
 if missing:raise ValueError('SOURCE_KERNEL_RETAINED_LEAF_UNAVAILABLE: '+', '.join(missing[:4]))
 retained={row['node_id']:copy.deepcopy(selected[row['node_id']]) for row in normalized['inputs']}
 frame=source_kernel.validate_publication_inputs(root,owned_workspace('sdk'),packet,retained=retained)['frame']
 return {'schema_version':CARRY_SCHEMA,'packet':copy.deepcopy(packet),'retained':retained,
  'parent_basis':(parent or {}).get('publication_handle'),
  'leaves':{lid:copy.deepcopy(leaf['projection']) for lid,leaf in sorted(frame['leaves'].items())},
  'currentness':copy.deepcopy(frame['currentness'])}


def is_close_carry(value):
 return isinstance(value,dict) and value.get('schema_version')==CARRY_SCHEMA


def published_currentness(inputs,nodes):
 """The packet and per-row currentness a publication receipt records.

 The carry's states are those of the validation that produced the published leaves: input_frame,
 the deposit's own validation (keeper.semantic_input_frame), refuses SOURCE_KERNEL_CURRENTNESS_MOVED
 when its states differ from the carry's. Here a published leaf that is not the validated one
 refuses with the same code rather than mislabel the receipt.
 """
 if not is_close_carry(inputs):return inputs,None
 for lid,projection in inputs['leaves'].items():
  if not isinstance(nodes.get(lid),dict) or nodes[lid].get('projection')!=projection:
   raise ValueError('SOURCE_KERNEL_CURRENTNESS_MOVED: '+lid)
 return inputs['packet'],inputs['currentness']


def counts(currentness):
 """The four state counts the close receipt and the wake show."""
 rows=(currentness or {}).values()
 return {state.lower():sum(1 for row in rows if row.get('state')==state) for state in ('CURRENT','CARRIED','STALE','UNKNOWN')}


def input_frame(root,selections=None):
 """Selected leaves and their currentness.

 Only a close carry (laplace.source-close-carry/1, made by close_inputs for the ordinary close)
 publishes STALE and UNKNOWN rows as their retained parent leaves. The active packet and a list
 of requests are fresh selection: a STALE or UNKNOWN row refuses SOURCE_KERNEL_SOURCE_<STATE>.
 """
 from laplace.work import source_kernel
 from laplace.work.owner_discovery import owned_workspace
 value=coverage_inputs(root) if selections is None else selections
 if is_close_carry(value):
  frame=source_kernel.validate_publication_inputs(root,owned_workspace('sdk'),value['packet'],retained=value['retained'])['frame']
  # The deposit publishes this validation's leaves; the receipt records the carry's states. They
  # must be one validation's: a state or leaf that moved since close_inputs refuses the deposit.
  moved=sorted(lid for lid in set(frame['currentness'])|set(value.get('currentness') or {})
   if frame['currentness'].get(lid)!=(value.get('currentness') or {}).get(lid)
   or (frame['leaves'].get(lid) or {}).get('projection')!=(value.get('leaves') or {}).get(lid))
  if moved:raise ValueError('SOURCE_KERNEL_CURRENTNESS_MOVED: '+', '.join(moved[:4]))
  return frame
 if isinstance(value,dict):
  return source_kernel.validate_publication_inputs(root,owned_workspace('sdk'),value)['frame']
 return source_kernel.input_frame(root,value)


def keeper_leaves(frame):
 """Adapter supplies its own explicit collection root; keeper stays generic."""
 leaves=dict(frame['leaves'])
 if leaves:
  leaves['operational://declared-source']={'name':'operational://declared-source',
   'kind':'declared-source-collection','essence':'Declared Source contract meaning',
   'keywords':['declared','source','contract'],'sealed':False,'semantic_parent':''}
 return leaves

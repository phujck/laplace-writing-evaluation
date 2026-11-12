"""User-facing guides of the existing Help owner; Markdown is a generated view.

These are reading instructions, never actions, progress records or permissions.
Reference paths name packaged documentation; they are not callable HTTP handles.
"""
from __future__ import annotations

GUIDE_DECLARATIONS = {'start': {'title': 'Start here',
           'summary': 'Read, write and organise a project. AI help is optional.',
           'sections': [{'id': 'choose-a-start',
                         'title': 'Choose a start',
                         'paragraphs': ['Start with Projects. Each project keeps related writing, sources, tasks '
                                        'and conversations together; reading and writing need no Task.',
                                        'Reading and manual writing need no AI account. Asking an AI needs a '
                                        'configured provider and an explicit Send.'],
                         'steps': ['Write: open or create an Article or Book, then Writing.',
                                   'Read: open a project, then Sources and Add local document.',
                                   'Organise: open Tasks; read the purpose, state and next action.',
                                   'Continue: use Home or Recent activity. Open a task and What led here to find '
                                   'its actual results.']},
                        {'id': 'keep-your-place',
                         'title': 'Keep your place',
                         'paragraphs': ['Help explains this screen; recipes show routes, the glossary explains '
                                        'states, and advanced reference names detailed guides.',
                                        'A completed task can need current review or lack supporting raw; '
                                        'its achievement stays recorded.',
                                        'Looking elsewhere never sends or retargets a message. Inspect context '
                                        'before Send; check an uncertain original request before '
                                        'trying again.'],
                         'references': [{'label': 'Task recipes',
                                         'guide': 'tasks',
                                         'path': 'docs/writing-tasks.md'},
                                        {'label': 'Glossary',
                                         'guide': 'glossary',
                                         'path': 'docs/writing-glossary.md'},
                                        {'label': 'Advanced reference',
                                         'guide': 'reference',
                                         'path': 'docs/writing-reference.md'}]}]},
 'tasks': {'title': 'Task recipes',
           'summary': 'Find your project, do a task, inspect its outcome and return without losing your '
                      'place.',
           'sections': [{'id': 'open-or-create-a-project',
                         'title': 'Open or create a project',
                         'paragraphs': ['No AI account is needed.'],
                         'steps': ['Choose Projects. Open a title or Create a project.',
                                   'For writing, enter a title and purpose and choose Article or Book, then '
                                   'Create project. A General project does not automatically offer Writing.',
                                   'On Home choose Writing, Sources or Tasks. If Writing is absent, use Add '
                                   'manuscript only when offered, or choose an Article or Book through Projects.',
                                   'Use the workspace menu for other projects and Activity. Research is the '
                                   'project literature, calculations and proofs; relationships and system '
                                   'tools are optional.']},
                        {'id': 'read-a-source-and-ask-a-question',
                         'title': 'Read a source and ask a question',
                         'paragraphs': ['Reading needs no AI account; Send needs a provider. Linked material comes '
                                        'first with Read; Manage holds its other controls.'],
                         'steps': ['Choose Sources, then Add local document. Select a PDF or UTF-8 text file and '
                                   'check its destination.',
                                   'Leave Show this document in Sources checked to add its entry, then Add '
                                   'document. The original is saved; no message is sent.',
                                   'After success, View in Sources. For an unfinished entry, Check project before '
                                   'adding to Sources, then Add saved original to Sources when offered; do not '
                                   'upload a duplicate.',
                                   'Choose Inspect document text or Inspect PDF text. Read the shown passage/page '
                                   'and coverage, then Use in conversation to select it.',
                                   'Before Send, use Inspect context beside the destination to check the reading. '
                                   'Next message sets future intent, not permission. An inspected window is not the '
                                   'whole document.',
                                   "A file's Prepare a question about this file fills an unsent question; a "
                                   'filename alone is not inspected text.',
                                   'Find literature or Add to Literature keeps that claim or passage as the '
                                   'target; a link is not support.'],
                         'references': [{'label': 'Document reading and interrupted imports',
                                         'path': 'docs/writing-workspace.md'}]},
                        {'id': 'write-save-and-reopen',
                         'title': 'Write and return to saved text',
                         'paragraphs': ['Manual writing needs no AI account. A document may be an authored draft '
                                        'even when every edit is saved.'],
                         'steps': ['Choose Writing or Continue writing in a writing-enabled project. Otherwise '
                                   'see Open or create a project.',
                                   'Click a paragraph to write. Ctrl-S or Save changes writes it; until then the '
                                   'draft stays in the editor, even across a reload. Autosave is off by default.',
                                   'Sources beside writing opens a saved source without replacing the editor. '
                                   'Inspect its coverage; browsing does not replace the message target.',
                                   'Change source opens choices; Close sources closes the pane. Back to writing '
                                   'and Return to source keep both places.',
                                   'On a narrow screen an open Conversation fills the pane: Back to reading returns '
                                   'to the text, and Show source instead opens the source there.',
                                   'Leave and reopen Writing to check saved text. Each save warning offers Keep my '
                                   'text and save it first.',
                                   'PDF is built separately. No verified PDF means no verified build is '
                                   'available, not that none was built. '
                                   'Build stays explicit in Document tools, with Undo, Redo, Drafts and '
                                   'Document setup.']},
                        {'id': 'organise-tasks-and-reviews',
                         'title': 'Organise tasks and reviews',
                         'paragraphs': ['Planning a task does not start it. Review questions can be saved without '
                                        'approving an AI reviewer.'],
                         'steps': ['Choose Tasks. Open a purpose, state, reason and next action. Add task creates '
                                   'a goal with a completion condition.',
                                   'Plan this task sets priority, order or deferral when offered. Saving records '
                                   'intention, not execution or approval.',
                                   'Set up reviews: enter questions and each required Review scope, then Save '
                                   'review questions.',
                                   'Optional reviewer approvals: inspect scope/duration before Save questions and '
                                   'selected approvals. This does not start a review.',
                                   'Now names who is acting and the one turn a Stop would touch; Next lists the '
                                   "owner's permitted actions by kind: a form here, an owner-issued template "
                                   'shown as issued, or an inspect-only read. Ready or proof arrival is not '
                                   'acceptance or permission to mark done.'],
                         'references': [{'label': 'Review setup, responses and recovery',
                                         'path': 'docs/writing-work-review-lifecycle.md'}]},
                        {'id': 'revise-from-a-comment',
                         'title': 'Revise a passage from a comment',
                         'paragraphs': ['A comment, proposal, applied change, build and your decision are separate '
                                        'records; the Revision chain shows which exist.'],
                         'steps': ['Right-click a paragraph, choose Comment on this passage and Save comment; math '
                                   'or code is never split. Unsent drafts await your choice. If the reply is lost, '
                                   'Check save keeps your text and posts nothing twice.',
                                   'Ask for a revision in Conversation or request an offered review; responses show '
                                   'each reply and change no text.',
                                   'Open a proposal with Review in manuscript and compare it with the current '
                                   'passage; if it changed, re-read rather than retry.',
                                   'Apply only edits you accept; applied text is a source change, not accepted '
                                   'science.',
                                   'Build, read the PDF, then record your decision and its evidence on the task.']},
                        {'id': 'find-what-happened',
                         'title': 'Find what happened and where the result went',
                         'paragraphs': ['A Task can link conversations, sources and reviews; sources and '
                                        'documents also work without one.'],
                         'steps': ['Choose Tasks, open the task and What led here. Read its purpose, latest '
                                   'outcome and event dates.',
                                   'Follow offered Read reply, Open conversation, Read file, Read review, Read '
                                   'Source basis or Read run links. History metadata is not body inspection; '
                                   'pages and changed-input restarts stay explicit.',
                                   'A bound conversation belongs to this Task. Associated evidence is not native '
                                   'execution; a summary is not an unavailable exact reply.',
                                   'Follow the result destination and return control. Recent activity records '
                                   'events, not current jobs; a reply or completion is not a release.']},
                        {'id': 'finish-a-task',
                         'title': 'Finish a task without losing its evidence',
                         'paragraphs': ['Required reviews, prerequisites and evidence must satisfy this task. '
                                        'Handoff or synthesis alone does not close it.'],
                         'steps': ["Read the task's reason and next action. Historical Done can need current "
                                   'review; that alone is not failed tests or unfinished implementation.',
                                   'Open Update task status. Distinguish the saved record from your change; '
                                   'choose Mark done under Task status only when offered.',
                                   'Choose saved evidence selects saved project items or run outputs; advanced '
                                   'exact paths remain available.',
                                   'Enter a Reason or completion summary, then Save task status. Inspect refusals '
                                   'rather than bypassing or renewing reviews. Check an uncertain original '
                                   'request before resending.',
                                   'Done, review, support, adoption, integration, release and cleanup differ; a verdict '
                                   'is history. Unavailable output is gone; use issued reads.']},
                        {'id': 'use-a-workflow',
                         'title': 'Use a workflow',
                         'paragraphs': ['A workflow is an optional reusable set of steps, such as drafting and '
                                        'reviewing; reading and writing need none.'],
                         'steps': ['Open Workflows. Choose a saved workflow or New workflow and read its purpose '
                                   'and project/workspace ownership.',
                                   'In Design, write steps, then Check execution. '
                                   'Save definition records '
                                   'a version; unsaved edits stay local.',
                                   'Browse saved versions pages history; Read saved version and Read next '
                                   'saved-body part open text; Close saved version keeps the draft and save check.',
                                   'Runs reads recorded project-workflow uses. Use as new draft copies a saved '
                                   'version to a chosen owner; Prepare agent run needs it saved. Prepare external '
                                   'run is the CLI path.',
                                   'Preparation is not execution; Send and start/apply stay explicit. An '
                                   'unsupported view does not prove no run exists.',
                                   'To share a saved workflow, open it from Explore across projects as a Workflow '
                                   'Definition, then Open Handover. Prepare, inspect the manifest and export to a '
                                   'fresh local directory; lineage export works the same way.'],
                         'references': [{'label': 'Workflow editing and supported preparation',
                                         'path': 'docs/writing-workflow-editor.md'},
                                        {'label': 'What a selected handover carries',
                                         'path': 'docs/project-data-handover.md'}]},
                        {'id': 'find-help-and-recover',
                         'title': 'Find Help and recover',
                         'paragraphs': ['Help can explain and navigate. It never submits, approves, sends or '
                                        'applies work for you.'],
                         'steps': ['Open Help at the confusing decision. Read its purpose, next action/effects or '
                                   'a task recipe.',
                                   'Back or Close returns to its current opener unless you deliberately moved '
                                   'elsewhere. Previous object, containing scope and leaving Task context have '
                                   'different destinations.',
                                   'For an uncertain request, keep the original and use its Check or Inspect '
                                   'action; Unknown does not mean no effect.',
                                   'Open the conversation or run for current execution; Advanced details keep '
                                   'exact identities.'],
                         'references': [{'label': 'Supported account setup',
                                         'path': 'docs/writing-account-setup.md'}]}]},
 'glossary': {'title': 'Glossary',
              'summary': 'The few distinctions that keep your work and choices clear.',
              'sections': [{'id': 'writing-and-reading',
                            'title': 'Writing and reading',
                            'paragraphs': ['Project: related writing, sources, tasks and conversations.',
                                           'Draft: an authored draft document can already be saved; a workflow '
                                           'local draft has unsaved version changes.',
                                           'Saved: the app recorded this change. A PDF build or independent '
                                           'judgement is separate.',
                                           'Source: a document or project file. Linking an existing source '
                                           'is advanced; importing a local document needs no path. Developer '
                                           'Source is application code.',
                                           'Inspected reading: only the exact window/page opened, not unseen '
                                           'remainder.',
                                           'Message target: the retained reading/object for the next message; '
                                           'browsing does not replace it.']},
                           {'id': 'tasks-and-results',
                            'title': 'Tasks and results',
                            'paragraphs': ['Task (Work): a goal with prerequisites and completion conditions. A '
                                           'programme has its own conditions; one run does not close it.',
                                           'Ready: current prerequisites allow a next action, not necessarily '
                                           'Done. Waiting: something required is unresolved, not automatically a '
                                           'failed test.',
                                           'In progress is declared standing. Running needs current observed '
                                           'execution, even after an older Done. No current '
                                           'observation does not mean it never ran.',
                                           'Review: a judgement on evidence. Required questions need current '
                                           'satisfaction and independence when required; reviewer approval is '
                                           'permission, not that judgement.',
                                           'Prepared completion: frozen Source, declared proof slots, approved '
                                           'review return. Declared proof arrival is not acceptance. Continue: one '
                                           'owner-checked handoff and review request.',
                                           'Done with current review needed: the achievement stays recorded while '
                                           'changed scope/evidence needs inspection. Unknown means current proof '
                                           'could not be established, not failure.',
                                           'Evidence availability: declared supporting items may be '
                                           'present, changed or unavailable; direct completion records can '
                                           'match while old raw is missing, and legacy support may be undeclared.',
                                           'Activity: recorded events and destinations; old engine '
                                           'work orders/promises are not Tasks or running jobs.',
                                           'Local accepted, live, distributed: reviewed candidate, running app '
                                           'and published edition. Each needs its own dated record; counts prove '
                                           'no such join.']},
                           {'id': 'workflows-and-recovery',
                            'title': 'Workflows and recovery',
                            'paragraphs': ['Workflow: reusable saved steps. Save, prepare and start are separate.',
                                           
                                           'Run: one attempt on particular inputs/settings, not task acceptance.',
                                           
                                           'Context is delivered content; grouping inherits no transcript or '
                                           'permission and starts no child.',
                                           'Approval permits bounded future action; it starts nothing.',
                                           
                                           
                                           
                                           'Uncertain request or Stop: keep and check the original; never resend automatically. '
                                           'Resend original Stop unchanged repeats it once; it is not a new Stop. Stopped: gated, every child settled.',
                                           'Exact details: owner, reference, basis and receipt identify what was '
                                           'read/changed.',
                                           'Handover: permitted content copied to a fresh recipient home. '
                                           'Accounts, grants, host proof and unsaved browser state do not travel '
                                           'as authority.']}]},
 'reference': {'title': 'Advanced reference',
               'summary': "Detailed guides are included in the package's docs folder. These are locations, not "
                          'execution controls.',
               'sections': [{'id': 'reference-guides',
                             'title': 'Reference guides',
                             'paragraphs': ['Use task recipes first. These packaged guides explain setup, exact '
                                            'behavior and limits.',
                                            'The download guide states source and data cutoffs; live workspace, '
                                            'accounts and host qualification do not automatically travel.'],
                             'references': [{'label': 'Download and installation',
                                             'path': 'docs/writing-container-download.md'},
                                            {'label': 'Accounts and platform prerequisites',
                                             'path': 'docs/writing-account-setup.md'},
                                            {'label': 'Connected workspace reference',
                                             'path': 'docs/writing-workspace.md'},
                                            {'label': 'Workflow editor',
                                             'path': 'docs/writing-workflow-editor.md'},
                                            {'label': 'Review lifecycle',
                                             'path': 'docs/writing-work-review-lifecycle.md'},
                                            {'label': 'Task outcomes and supporting evidence',
                                             'path': 'docs/writing-evidence-navigation.md'},
                                            {'label': 'Selected project handover',
                                             'path': 'docs/project-data-handover.md'},
                                            {'label': 'Developer and owner reference',
                                             'path': 'docs/writing-code-overview.md'}]}]}}

def render_guide_markdown(guide_id: str) -> str:
    """The package document is the same content the existing Help read serves."""
    guide = GUIDE_DECLARATIONS[guide_id]
    lines = ["<!-- Generated from laplace.native.help_guides; edit that canonical Help content. -->",
             "# " + guide["title"], "", guide["summary"], ""]
    for section in guide["sections"]:
        lines += ["## " + section["title"], ""]
        for text in section.get("paragraphs", []):
            lines += [text, ""]
        for number, text in enumerate(section.get("steps", []), 1):
            lines += [str(number) + ". " + text]
        if section.get("steps"):
            lines.append("")
        for reference in section.get("references", []):
            lines += ["- [" + reference["label"] + "](" + reference["path"].removeprefix("docs/") + ")"]
        if section.get("references"):
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

"""A project-wide view derived from the existing research and writing organs.

No second workflow ledger is created. Stages describe available material and
unresolved work; empirical or formal evidence is required only when the claim
requires it. A connected authoring scope survives every stage.
"""
from __future__ import annotations

from laplace.writing import records as writing_records
import json
from pathlib import Path


def _outstanding_stale_proposals(root: Path, project: str, stale: list[dict]) -> list[dict]:
    """Fold full context audit history to unapplied edit proposals only."""
    stale_ids = {row.get("context_id") for row in stale if row.get("context_id")}
    records = writing_records.fold_records(root)
    outstanding = set()
    for turn in records.get("turns", {}).values():
        proposal = ((turn.get("reply") or {}).get("proposal") or {})
        edits = proposal.get("edits") if isinstance(proposal, dict) else None
        if (turn.get("project") == project and turn.get("context_id") in stale_ids
                and isinstance(edits, list) and edits
                and not (turn.get("application") or {}).get("complete")):
            outstanding.add(turn["context_id"])
    return [row for row in stale if row.get("context_id") in outstanding]



def _programme_projection(project, root, *, work, research, source, preview):
    """Add the coherent programme without breaking the legacy seven-stage view.

    Summary reads expose exact descents instead of eagerly qualifying every
    claim, reconstructing reader history or treating a build as export proof.
    """
    from laplace.writing import stages, prepared_work
    recipe = stages.programme(root)
    phases = []
    for phase in recipe["phases"]:
        observation = {"status": "NOT_OBSERVED", "read": phase["read"],
                       "acceptance": "NOT_ASSESSED"}
        if phase["id"] == "results":
            observation.update(status="INPUTS_AVAILABLE" if research.get("results") else "NOT_OBSERVED",
                result_count=len(research.get("results") or []),
                currentness=research.get("currentness") or {},
                qualification="Record availability/currentness only. Read the scoped claim/result binding and interpretation.")
        elif phase["id"] == "literature":
            observation["qualification"] = ("Read the exact scoped literature_scope, including pagination. "
                "Passage-qualified support can be usable before citation/build completion. "
                "BibTeX pins are not passage receipts. No search or reading is claimed by this projection.")
        elif phase["id"] == "improvement":
            observation["qualification"] = ("Read authored reader-state/paragraph diagnostics and their coverage/currentness. "
                "They are not independent reader judgement or scientific validity.")
        elif phase["id"] == "draft":
            observation.update(source_status=source.get("status"),
                qualification="A selected file is not a completed draft. Existing guarded authorized application "
                    "preserves direct author Save and requires no repeated human permission gate.")
        elif phase["id"] == "export":
            observation.update(build_status=preview["status"],
                qualification="Build availability only. Inspect actual pages and a separate export/delivery receipt.")
        else:
            observation["qualification"] = ("Exact independent reading/disposition required." if phase["id"] == "judgement"
                                            else "Original parent must consume all exact returns, including rejected outcomes.")
        phases.append({**phase, "observation": observation})
    programmes = [row for row in work.get("tasks", [])
                  if prepared_work._programme_opt_in(row)]
    # Existing Work owns all instances. Keep this descent bounded and leave the
    # rest discoverable through the ordinary Work catalogue, not another store.
    routes = [prepared_work.programme_route(project, root, row["id"]) for row in programmes[:3]]
    return {**recipe, "phases": phases, "create_action": prepared_work.programme_create_action(project, root),
            "routes": routes, "routes_omitted": max(0, len(programmes) - len(routes)),
            "routes_read": {"operation": "project", "payload": {"view": "catalogue", "q": "writing"}},
            "legacy_stages": "The top-level stages/next_action fields remain the compatibility view. "
                "programme owns the ordered manuscript route. Maintenance writing_stage IDs are unchanged."}


def inspect(project: str, root: Path, *, include_history: bool = True) -> dict:
    from laplace.pipeline import authoring, projection_spec
    from laplace.manuscript import manuscript_source, document_style
    from laplace.research import concepts as concepts_surface, visuals_surface
    from laplace.work import project_work
    from laplace.research import research_catalogue
    root = Path(root).resolve()
    source = manuscript_source.resolve(project, repo_root=root)
    auth = authoring.load(project, repo_root=root)
    state_path, _ = authoring._state_path(project, root)
    manuscript = root / source["manuscript_dir"] if source.get("manuscript_dir") else state_path.parent
    research = research_catalogue.state_payload(project, root=root) or {}
    concepts = concepts_surface.state(project, root=root) or {}
    visual_reply = visuals_surface.handle('/visuals/state', {'project':[project]}, 'GET', b'', repo_root=root)
    visuals = json.loads(visual_reply[2]) if visual_reply and visual_reply[0] == 200 else {}
    spec = projection_spec.load_spec(project, root) or {}
    traversal = manuscript_source.traversal(source['root'], repo_root=root) if source.get('status') == 'resolved' else {'files':[]}
    if include_history:
        try:
            contexts = authoring.inspect(project, repo_root=root)
        except ValueError as exc:
            contexts = {'stale': [], 'diagnostics':[str(exc)]}
    else:
        # Ordinary workspace reads need the actionable proposal queue, not a
        # replay of every historical context. Exact historical staleness remains
        # available through the explicit audit view.
        from laplace.manuscript import proposal_currentness
        records=writing_records.fold_records(root);pending=[]
        for turn in records.get("turns",{}).values():
            if turn.get("project")!=project:continue
            view=proposal_currentness.proposal_view(turn,records=records)
            proposal=view.get("proposal")
            if isinstance(proposal,dict) and proposal.get("edits") and view.get("proposal_state") in {
                    "ready","partial-application","saved-without-final-reply"}:
                pending.append({"context_id":turn.get("context_id"),"turn_id":turn.get("id"),
                                "reasons":["unapplied-proposal"]})
        contexts={"stale":pending,"diagnostics":[]}
    work = project_work.state(project, root) if include_history else project_work.summary(project, root)
    framing = auth.get('framing') or {}
    stages = []
    def stage(ident, title, status, summary, prompt, producers, consumers):
        stages.append({'id':ident,'title':title,'status':status,'summary':summary,'prompt':prompt,
                       'producers':producers,'consumers':consumers})
    missing = [k for k in ('purpose','audience','question') if not framing.get(k)]
    genre = (spec.get('manuscript') or {}).get('genre')
    stage('framing','Purpose, reader & form','DRAFT' if missing else 'AVAILABLE',
          'Set '+', '.join(missing)+'.' if missing else 'The project has an explicit question and reader'+(f'; form: {genre}.' if genre else '; choose its form.'),
          'Work with me on the purpose, intended reader, central question and form of this manuscript. Inspect the existing argument and scientific work first. Make the framing specific enough to guide research and writing, preserve unresolved choices, and save agreed framing through the project tool.',
          [str(state_path.relative_to(root)),str(manuscript/'manuscript_spec.json')],['research goals','argument','manuscript form'])
    glossary = concepts.get('glossary') or []
    relations = concepts.get('relations') or []
    stage('concepts','Concepts, claims & dependencies','AVAILABLE' if concepts.get('focus',{}).get('id') else 'MISSING',
          f'{len(glossary)} glossary entries visible; focused view has {len(relations)} declared relations. Definitions and dependency types need scientific review.',
          'Inspect and develop the conceptric supporting this manuscript. Make definitions, assumptions, result statements, source links and logical dependencies explicit. Separate prerequisite, evidential support, implementation and analogy. Use stable identities and projection metadata for glossary terms and manuscript references. Identify unsupported claims and create useful research tasks; do not equate metadata with verification.',
          ['corpus network','rewire ledger'],['glossary','result verification','causal and explanatory order'])
    research_state = research.get('state', 'UNKNOWN')
    currentness = research.get('currentness',{}).get('status','UNKNOWN')
    if research_state == 'COMPLETE' and currentness == 'CURRENT':
        rstatus = 'AVAILABLE'
    elif currentness == 'STALE' or research_state == 'REFUSED':
        rstatus = 'STALE'
    elif research.get('experiments') or research.get('results') or research.get('producers'):
        rstatus = 'DRAFT'
    else:
        rstatus = 'MISSING'
    stage('research','Literature, numerics & proof',rstatus,
          f"{len(research.get('experiments',[]))} experiment records; {len(research.get('results',[]))} result records. "+research.get('currentness',{}).get('reason','No evidence records yet.'),
          'Inspect this project’s claims and existing literature, numerical producers, results and formal checks. Decide which evidence each claim actually needs. Read local source attachments when relevant, retain limitations, and develop reproducible experiments or formalisation where warranted. Record exact inputs, outputs and claim associations. Process success alone is not scientific acceptance.',
          ['references.json','research_records.json','research_producers.json','formal/manifest.json'],['result conceptrics','claims','figures','writing context'])
    argument = str(auth.get('argument') or '')
    stage('argument','Connected argument & manuscript shape','DRAFT' if not argument or argument == framing.get('purpose') else 'AVAILABLE',
          'A sustained argument is recorded.' if argument and argument != framing.get('purpose') else 'Develop the explanation beyond the initial project purpose.',
          'Develop the manuscript as one sustained explanation. Begin with the problem that makes the next idea necessary; connect theory, construction, evidence and consequences. Inspect the conceptric, goals and existing prose. Keep scientific dependencies distinct from pedagogical order. Save the connected argument and propose a book/chapter structure; preserve continuous context rather than assigning disconnected section prose.',
          ['authoring.json','manuscript_spec.json','projection_plan.json'],['chapter structure','connected authoring scope','reader review'])
    stage('manuscript','Draft, discuss & revise','AVAILABLE' if traversal.get('files') else 'MISSING',
          f"{len(traversal.get('files',[]))} source files in the selected edition. "+('Source is read-only.' if source.get('read_only') else 'Direct edits and accepted revisions are versioned.'),
          'Continue this manuscript’s connected argument. Inspect the selected prose, neighbouring context, applicable author feedback and evidence. Discuss uncertainties with me and return reviewable source-addressed edits. Preserve local author intent, citations, mathematical qualifications, glossary identities and cross-references.',
          traversal.get('files',[]),['reader view','review feedback','compiled document'])
    audit_stale = contexts.get('stale') or []
    stale = _outstanding_stale_proposals(root, project, audit_stale)
    feedback = auth.get('corrections') or []
    stage('review','Review & change propagation','STALE' if stale else 'OPEN',
          f'{len(stale)} authoring contexts need reconsideration; {len(feedback)} comments or edit examples available. Independent judgement remains explicit.',
          'Review the complete connected explanation against its purpose and reader. Inspect source and evidence currentness, logical gaps, definitions and notation, numerical/formal limitations, citations, figure meaning and cross-references. Consume the author’s direct edits and comments. Produce concrete, independently checkable findings and scoped revision work; do not award scientific verification to your own production.',
          ['feedback/feedback.jsonl','authoring.json','work_orders.jsonl'],['affected research tasks','fresh writing contexts','author decisions'])
    specs = visuals.get('specs') or []
    stale_figures = [s['id'] for s in specs if s.get('render_freshness')=='STALE']
    unrendered_figures = [s['id'] for s in specs if s.get('render_freshness')!='CURRENT']
    try:
        from laplace.manuscript import document
        preview = {'status':document.current(project,root,include_preview=False)['status']}
    except ValueError:
        preview = {'status':'NOT_BUILT'}
    presentation_status = ('STALE' if stale_figures or preview['status']=='STALE' else
                           'DRAFT' if unrendered_figures else
                           'AVAILABLE' if specs or preview['status']=='READY' else 'DRAFT')
    stage('presentation','Visuals, style & publication',presentation_status,
          f'{len(specs)} visual specifications; {len(stale_figures)} stale and {len(unrendered_figures)} not-current renders. Current document output: {preview["status"].lower().replace("_"," ")}.',
          'Review how this manuscript communicates visually. Use the house style and document profile for plots and conceptual diagrams; retain data and relation semantics. Inspect generated assets before explicit placement, check captions and cross-references, build the document and assess the rendered pages. Preserve authored prose while trying presentation changes.',
          ['manuscript_spec.json','figure_manifest.json','document_style.json','selected TeX source'],['asset inventory','inline figures','PDF','publication review'])
    next_task = work.get('next')
    next_action = 'framing' if missing else 'concepts' if not concepts else 'argument' if not argument or argument==framing.get('purpose') else 'review' if stale else 'research' if next_task else 'manuscript'
    return {'schema_version':'laplace.writing-pipeline/1','project':project,'stages':stages,
            'next_action':next_action,'next_task':next_task,
            'programme':_programme_projection(project, root, work=work, research=research, source=source, preview=preview),
            'gaps':[{'stage':s['id'],'status':s['status'],'reason':s['summary']} for s in stages if s['status'] in {'MISSING','DRAFT','STALE','UNKNOWN'}],
            'propagation':research.get('invalidation',[]), 'stale_contexts':stale,
            'historical_stale_context_count':len(audit_stale) if include_history else None,
            'historical_context_audit':{'operation':'pipeline','payload':{'view':'audit'}},
            'principle':'Evidence identities are fine-grained; writing follows a connected argument. Stage availability is not scientific verification.'}

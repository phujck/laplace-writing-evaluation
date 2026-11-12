"""Original/read/bind on an explicitly synthetic authored local document."""
from __future__ import annotations
from .core import PROJECT

def run(root, rec):
    from laplace.native import tools
    from laplace.research import literature_support
    from laplace.pipeline import registry
    def call(name, op, payload):
        return rec.call("literature-"+name, tools.execute, root, PROJECT, "work", op, payload)
    body = ("This is a synthetic author-supplied example, not a published reference.\n"
            "The illustrative ordered sequence is 1, 2, 3.\n"
            "No empirical inference or general scientific result is established.\n")
    artifact=call("original-artifact","store_artifact",{
        "scope":"project","path":"examples/original-sequence.txt","before":None,"content":body,
        "reason":"Keep the exact illustrative local source in owner custody."})
    registered=registry.resolve(PROJECT,repo_root=root)
    original=registered.path(registered.project_dir,root)/"examples/original-sequence.txt"
    imported=call("import","literature_import",{
        "metadata":{"title":"Authored sequence fixture","creators":["Example author"],
                    "year":"2026","item_type":"unpublished"},
        "provenance":{"description":"Explicitly synthetic local example, not external literature.",
                      "path":str(original)},"citekey":"AuthoredSequenceExample"})
    key=imported["association"]["key"]
    source=call("original","reference_source",{"key":key})
    read=call("read","reference_text",{"key":key,"limit":2000})
    receipt=read["reading_receipt"]
    revision=literature_support.meaning_revision(PROJECT,"def:sequence",root)
    payload={"key":key,"claim_id":"def:sequence","claim_revision":revision,
        "relation":"supports","rationale":"The authored source identifies only this explicit synthetic input.",
        "reading_status":"partial","reading_id":receipt["id"],
        "evidence":{"locator":receipt["locator"],"excerpt":"The illustrative ordered sequence is 1, 2, 3."}}
    rec.refuses("literature-stale-claim",ValueError,tools.execute,root,PROJECT,"work",
                "literature_bind",{**payload,"claim_revision":"sha256:"+"0"*64})
    bound=call("bind","literature_bind",payload)
    uses=call("uses","literature_uses",{"claim_id":"def:sequence"})
    scope=call("scope","literature_scope",{"node":"def:sequence"})
    # Preserve the good illustrated original. Exercise collision guards rather
    # than corrupting public source bytes or pretending to have reread them.
    rec.refuses("literature-original-collision",ValueError,tools.execute,root,PROJECT,"work",
        "store_artifact",{"scope":"project","path":"examples/original-sequence.txt",
                         "before":None,"content":"overwrite","reason":"Negative create collision."})
    return {"status":"EXECUTED","key":key,"original_artifact":artifact["id"],
        "reading_id":receipt["id"],"binding":bound,
        "manuscript_citation":"NOT_YET_EXERCISED: source fixture and reader placement are distinct",
        "qualification":"Authored synthetic documentary support only, no invented DOI or external literature verification"}

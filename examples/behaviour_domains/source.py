"""Real atomic-equation source edit -> issued history inverse -> exact-byte reopen.
No provider turn, transcript banking or fabricated independent acceptance.
"""
from __future__ import annotations
from .core import PROJECT

def run(root,rec):
    from laplace.native import tools
    from laplace.manuscript import manuscript_source
    def call(name,op,payload):
        return rec.call("source-"+name,tools.execute,root,PROJECT,"work",op,payload)
    selected=manuscript_source.resolve(PROJECT,repo_root=root)
    target=root/selected["manuscript_dir"]/"S1.tex"
    before=target.read_bytes()
    ordinary=call("ordinary-read","source",{"files":["S1.tex"],"line_start":2,"line_end":2})["sources"][0]
    rec.refuses("source-ordinary-paragraph-refusal",ValueError,tools.execute,root,PROJECT,"work",
        "block_change",{"operation":"delete","block":{"file":ordinary["file"],
        "line_start":2,"line_end":2,"before":ordinary["text"].removesuffix("\n"),
        "expected_source_digest":ordinary["expected_source_digest"]}})
    assert target.read_bytes()==before
    lines=before.decode("utf-8").splitlines()
    start=lines.index("\\begin{equation}")+1
    end=lines.index("\\end{equation}",start)+1
    read=call("read","source",{"files":["S1.tex"],"line_start":start,"line_end":end})
    observation=read["sources"][0]
    deleted=call("delete","block_change",{"operation":"delete","block":{
        "file":observation["file"],"line_start":start,"line_end":end,
        "before":observation["text"].removesuffix("\n"),
        "expected_source_digest":observation["expected_source_digest"]}})
    assert target.read_bytes()!=before
    ref=deleted["undo_ref"]
    inverse=call("inverse-read","author_history",
        {"view":"structural-undo","kind":ref["kind"],"id":ref["id"]})
    restored=call("undo","block_change",inverse["undo"])
    assert target.read_bytes()==before
    reread=call("reopen","source",{"files":["S1.tex"]})
    assert "The input sequence is 1, 2, 3." in reread["sources"][0]["text"]
    return {"status":"EXECUTED","deleted":deleted,"restored":restored,
        "before_sha256":rec.digest(target),"reopened_equal":target.read_bytes()==before,
        "qualification":"Actual source-owner undo and fresh read. Browser Manual Undo -> Save -> reopen remains coordinator-owned and is not inferred from this result."}

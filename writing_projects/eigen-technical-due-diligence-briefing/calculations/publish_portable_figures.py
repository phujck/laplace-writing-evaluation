"""Publish immutable copies of eleven reviewed figure PDFs inside the selected edition.
No source TeX, original figure or evidence record is edited. Scientific content is unchanged.
Inputs are explicitly hash pinned. Output directory is unique to the supervised run.
"""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--mode",required=True)
p.add_argument("--args-json",required=True)
p.add_argument("--result",required=True)
a=p.parse_args()
assert a.mode=="smoke" and json.loads(a.args_json)=={}
assets=json.loads("[{\"id\":\"dd-backend-change\",\"source\":\"manuscript/figures/generated/dd-backend-change.pdf\",\"sha256\":\"b12fd5d809059af0f6c57c9372c4d04febcf71acefc3b3b6f90c45e007966a08\"},{\"id\":\"dd-shared-register-price\",\"source\":\"manuscript/figures/generated/dd-shared-register-price.pdf\",\"sha256\":\"b14bbfbd74728a450d78b2165abc1783f75fb12512afc5751563f113db195ba2\"},{\"id\":\"dd-retention-trajectories\",\"source\":\"manuscript/figures/generated/dd-retention-trajectories.pdf\",\"sha256\":\"e3fd1623520c41c62481a5ffcd23e9aa6c8887b084a08de3a3b3c5d0c10f70cd\"},{\"id\":\"dd-global-local-feedback\",\"source\":\"manuscript/figures/generated/dd-global-local-feedback.pdf\",\"sha256\":\"43cfe04aca10d4b53dfdd3619c3cfd338ed70580279bd5718cb81c687fba19f8\"},{\"id\":\"dd-operator-projection\",\"source\":\"manuscript/figures/generated/dd-operator-projection.pdf\",\"sha256\":\"7d94866978362e2aedead4026d93306610d4035dd4d73666f672fa774f32f398\"},{\"id\":\"dd-gap-selection\",\"source\":\"manuscript/figures/generated/dd-gap-selection.pdf\",\"sha256\":\"cfe4740c85b7faabc89cc20377466cd07fb6be34b4989987a17c382b8bd79352\"},{\"id\":\"dd-memory-parity\",\"source\":\"manuscript/figures/generated/dd-memory-parity.pdf\",\"sha256\":\"2564fc60c7f42928e65468ef12f5df29c4eb4ddc04e070f9e412fdca38a139ef\"},{\"id\":\"dd-superarc-controls\",\"source\":\"manuscript/figures/generated/dd-superarc-controls.pdf\",\"sha256\":\"578cb4ad7f62ef17ddfb461199b4deaa81be05562c9e0bed4b7a1cf3715beb02\"},{\"id\":\"dd-retention-memory\",\"source\":\"manuscript/figures/generated/dd-retention-memory.pdf\",\"sha256\":\"bf78b1f01cd1f36f401f1927d54887b1e4074ee94028a0904aa9e918817adee4\"},{\"id\":\"dd-spectral-window\",\"source\":\"manuscript/figures/generated/dd-spectral-window.pdf\",\"sha256\":\"2cd6ad2afc5a4110384173a4eb2c61af07967dc9a6315d453fdf8bf786770689\"},{\"id\":\"dd-memory-mechanism\",\"source\":\"manuscript/figures/generated/dd-memory-mechanism.pdf\",\"sha256\":\"bd630cfc411b7bfdeed077d2621643cdab443cc3d00b169e855f3f1f16b6bdfb\"}]")
root=Path.cwd()
result=Path(a.result)
out=root/"manuscript"/"working-draft"/"figures"/("portable-"+result.stem)
out.mkdir(parents=True,exist_ok=False)
records=[]
for asset in assets:
    src=root/asset["source"]
    data=src.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    assert digest==asset["sha256"]
    dst=out/(asset["id"]+".pdf")
    with dst.open("xb") as f: f.write(data)
    assert hashlib.sha256(dst.read_bytes()).hexdigest()==digest
    records.append({"id":asset["id"],"path":str(dst.relative_to(root)),"source":asset["source"],"sha256":digest,"bytes":len(data),"tex_path":str(dst.relative_to(root/"manuscript"/"working-draft"))})
result.write_text(json.dumps({"schema_version":"dd.portable-figure-publication/1","status":"complete","scientific_content":"UNCHANGED byte-for-byte PDF copies","artifacts":records},indent=2)+"\n")
print(json.dumps({"figures":len(records),"output_directory":str(out.relative_to(root))}))

import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--mode",required=True);p.add_argument("--args-json",required=True);p.add_argument("--result",required=True)
a=p.parse_args();assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd();out=root/"manuscript"/"working-draft"/"figures"/("robot-"+Path(a.result).stem)
out.mkdir(parents=True,exist_ok=False)
rows=json.loads("[{\"id\":\"dd-conceptric-envelope\",\"path\":\"manuscript/figures/generated/dd-conceptric-envelope.pdf\",\"sha256\":\"c557be0648bb8a74309c5a2a1f5dc8f9f03cb9e3fd074dc5802ed4e678bd514d\"},{\"id\":\"dd-ai-tool-harness\",\"path\":\"manuscript/figures/generated/dd-ai-tool-harness.pdf\",\"sha256\":\"27de7270a4073688a3a60f944c24f1b6f7936e9193e7b1fec764c38e82abcf3a\"},{\"id\":\"dd-nested-work-sdk\",\"path\":\"manuscript/figures/generated/dd-nested-work-sdk.pdf\",\"sha256\":\"953a1ffa0171bcafd1d87f05c6c470e9e2474e83eca79699aacdcbe190feb5ca\"}]")
for row in rows:
    raw=(root/row["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row["sha256"]
    dst=out/(row["id"]+".pdf")
    with dst.open("xb") as f:f.write(raw)
    row["tex_path"]=str(dst.relative_to(root/"manuscript"/"working-draft"))
    row["pdf"]=str(dst)
Path(a.result).write_text(json.dumps({"status":"COMPLETE","assets":rows,"limitations":["Byte-verified publication of conceptual vector drawings, not scientific validation."]},indent=2)+"\n")
print(json.dumps({"published":len(rows)}))

"""Private PRESENTATION only: pin/copy original, assemble candidate, render. No science."""
import argparse, hashlib, json, pathlib, shutil, subprocess, zipfile, re, os
P=pathlib.Path.cwd().resolve()
BASE=P/"generic-overview-candidate-20261111"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def scoped(s):
    q=pathlib.Path(s)
    if str(q).startswith("writing_projects/eigen-technical-due-diligence-briefing/"):
        q=pathlib.Path(str(q).split("writing_projects/eigen-technical-due-diligence-briefing/",1)[1])
    q=(P/q).resolve()
    q.relative_to(P)
    return q
def cmd(args,cwd,log):
    p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=170)
    log.append({"argv":args,"exit_code":p.returncode,"output":p.stdout})
    if p.returncode: raise RuntimeError(p.stdout[-6000:])
    return p.stdout
def freeze():
    m=json.loads((BASE/"preservation/original-source-snapshot.json").read_text())
    pins=dict(m["build"]["input_revisions"])
    pins[m["bibliography"]["file"]]=m["bibliography"]["sha256"]
    pins[m["build"]["pdf"]]=m["pdf"]["content_revision"]
    records=[]
    for name,digest in pins.items():
        p=scoped(name); actual=sha(p)
        if actual!=digest.removeprefix("sha256:"): raise RuntimeError("Changed original: "+name)
        records.append({"original":name,"relative":str(p.relative_to(P)),"sha256":actual,"bytes":p.stat().st_size})
    archive=BASE/"preservation/private-original.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            for r in records:
                if hashlib.sha256(z.read(r["relative"])).hexdigest()!=r["sha256"]:
                    raise RuntimeError("Snapshot collision")
    else:
        with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as z:
            for r in records: z.write(P/r["relative"],r["relative"])
            z.write(BASE/"preservation/original-source-snapshot.json","selection-and-provenance.json")
    index={"private":True,"disposition":"EXCLUDE_PRESERVED","files":records,"archive":str(archive.relative_to(P)),"archive_sha256":sha(archive),"selection_identity":m["selection_identity"]}
    out=BASE/"preservation/archive-receipt.json"
    if out.exists():
        if json.loads(out.read_text())!=index: raise RuntimeError("Immutable snapshot index collision")
    else: out.write_text(json.dumps(index,indent=2)+"\n")
    return index
def build():
    spec=json.loads((BASE/"candidate-manifest.json").read_text())
    out=BASE/spec.get("output_directory","rendered")
    out.mkdir(exist_ok=True)
    bundle=out/"source"; bundle.mkdir(exist_ok=True)
    copied=[]
    src=scoped(spec["source_bundle"]["path"])
    if sha(src)!=spec["source_bundle"]["sha256"]: raise RuntimeError("Changed source bundle")
    source_spec=json.loads(src.read_text())
    for r in source_spec["source_files"]:
        dest=bundle/r["bundle_path"]; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(r["content"])
        copied.append({"path":r["bundle_path"],"sha256":sha(dest),"bytes":dest.stat().st_size})
    for r in spec["files"]:
        p=scoped(r["path"]); digest=sha(p)
        if digest!=r["sha256"].removeprefix("sha256:"): raise RuntimeError("Candidate input changed: "+r["path"])
        dest=bundle/r["bundle_path"]; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,dest)
        copied.append({"path":r["bundle_path"],"sha256":digest,"bytes":dest.stat().st_size})
    (bundle/"manifest.json").write_text(json.dumps({"private":True,"scientific_acceptance":"NOT_AWARDED","files":copied},indent=2)+"\n")
    logs=[]
    cmd(["latexmk","-pdf","-interaction=nonstopmode","-halt-on-error","-no-shell-escape","eigen-overview.tex"],bundle,logs)
    pdf=bundle/"eigen-overview.pdf"
    info=cmd(["pdfinfo",str(pdf)],bundle,logs)
    text=cmd(["pdftotext","-layout",str(pdf),"-"],bundle,logs)
    (out/"extracted.txt").write_text(text)
    (out/"build-command-log.json").write_text(json.dumps(logs,indent=2)+"\n")
    shutil.copyfile(pdf,out/"eigen-overview.pdf")
    log=(bundle/"eigen-overview.log").read_text(errors="replace")
    (out/"latex.log").write_text(log)
    pages=int(re.search(r"Pages:\s+(\d+)",info).group(1))
    images=out/"pages"; images.mkdir(exist_ok=True)
    cmd(["pdftoppm","-r","65","-png",str(pdf),str(images/"page")],bundle,logs)
    from PIL import Image, ImageOps, ImageDraw
    paths=sorted(images.glob("page-*.png"))
    for start in range(0,len(paths),6):
        canvas=Image.new("RGB",(1200,1300),"#bbbbbb")
        draw=ImageDraw.Draw(canvas)
        for j,p in enumerate(paths[start:start+6]):
            im=Image.open(p).convert("RGB"); im.thumbnail((390,610))
            x=(j%3)*400+(400-im.width)//2; y=(j//3)*650+30
            canvas.paste(im,(x,y)); draw.text(((j%3)*400+8,(j//3)*650+8),p.stem,fill="black")
        canvas.save(out/f"contact-{start//6+1:02d}.png")
    with zipfile.ZipFile(out/"portable-source.zip","w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.rglob("*")):
            if p.is_file() and p.suffix not in [".aux",".log",".fls",".fdb_latexmk",".out",".synctex",".gz",".blg"]:
                z.write(p,str(p.relative_to(bundle)))
    warnings=[x for x in log.splitlines() if any(w in x for w in ["Overfull","Underfull","undefined","Warning"])]
    result={"kind":"PRESENTATION","scientific_inference":False,"private":True,"pages":pages,"pdf":str((out/"eigen-overview.pdf").relative_to(P)),"pdf_sha256":sha(out/"eigen-overview.pdf"),"bundle":str((out/"portable-source.zip").relative_to(P)),"bundle_sha256":sha(out/"portable-source.zip"),"source_files":copied,"warnings":warnings,"unresolved_references":bool(re.search(r"undefined|Citation.+undefined",log)),"contacts":[str(p.relative_to(P)) for p in sorted(out.glob("contact-*.png"))]}
    (out/"output-receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    return result
a=argparse.ArgumentParser(); a.add_argument("--mode"); a.add_argument("--args-json"); a.add_argument("--result"); a=a.parse_args()
res={"kind":"PRESENTATION","original_snapshot":freeze()}
if a.mode=="full": res["candidate"]=build()
pathlib.Path(a.result).write_text(json.dumps(res,indent=2)+"\n")

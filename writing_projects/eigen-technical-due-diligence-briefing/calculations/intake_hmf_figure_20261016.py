import argparse,base64,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()
src=Path('inputs/hmf-physical-ground-figure-20261016.json');d=json.loads(src.read_text());b=base64.b64decode(d['data']);assert hashlib.sha256(b).hexdigest()==d['sha256']
out=Path(a.result).with_suffix('');out.mkdir(exist_ok=True);pdf=out/'hmf-physical-ground-prediction.pdf';pdf.write_bytes(b)
Path(a.result).write_text(json.dumps({'scope':'Exact figure-byte intake from the HMF project. Presentation only; no experiment or scientific verification rerun.','source':{k:v for k,v in d.items() if k!='data'},'checks':{'source_pdf_hash_matches':True},'artifacts':[{'id':'hmf-physical-ground-prediction','pdf':str(pdf)}]},indent=2))

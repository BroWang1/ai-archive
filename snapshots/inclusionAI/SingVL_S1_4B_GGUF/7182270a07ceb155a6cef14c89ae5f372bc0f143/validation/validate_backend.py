"""Optional CPU reference test after compiling the external adapter."""
import sys,os,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'examples/llama_cpp'))
from model import SingVLS1
from cases import cases
p=argparse.ArgumentParser();p.add_argument('--variant',choices=['bf16','q8_0','q4_k_m'],default='q8_0');p.add_argument('--probability-tolerance',type=float,default=1e-5);a=p.parse_args()
files={'bf16':'SingVL-4B-BF16.gguf','q8_0':'SingVL-4B-Q8_0.gguf','q4_k_m':'SingVL-4B-Q4_K_M.gguf'}
os.environ['JEV_GGUF_MODEL']=str(ROOT/'models'/files[a.variant]);os.environ['JEV_GGUF_MMPROJ']=str(ROOT/'models/mmproj-SingVL-4B-F16.gguf')
refs={r['case']:r for r in map(json.loads,(ROOT/f'validation/reference_{a.variant}.jsonl').read_text().splitlines())}
m=SingVLS1(ROOT/'config');max_delta=0.;count=0
try:
 for name,state,questions,images in cases():
  response,details=m.predict(state,questions,images)
  def compare(x,y):
   global max_delta
   if isinstance(x,dict):
    assert x.keys()==y.keys()
    for key in x:compare(x[key],y[key])
   elif isinstance(x,(int,float)):max_delta=max(max_delta,abs(x-y));assert abs(x-y)<=a.probability_tolerance,(name,x,y)
   else:assert x==y,(name,x,y)
  compare(response['answers'],refs[name]['answers'])
  for qid,d in details.items():
   for key in ['input_ids_sha256','positions','image_grid_thw']:assert d[key]==refs[name]['details'][qid][key],(name,qid,key)
   count+=1
finally:m.close()
print(json.dumps({'complete':True,'variant':a.variant,'questions':count,'max_answer_numeric_delta':max_delta}))

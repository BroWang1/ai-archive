"""Validate protocol/preprocessing without loading a model or any native library."""
import sys,json,hashlib,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from processing import Processor,decode_answer
from cases import cases
p=Processor(ROOT/'config');result=[]
refs={mode:{r['case']:r for r in map(json.loads,(ROOT/f'validation/reference_{mode}.jsonl').read_text().splitlines())} for mode in ['bf16','q8_0','q4_k_m']}
def compare(a,b):
 if isinstance(a,dict):
  assert a.keys()==b.keys(),(a,b)
  for key in a:compare(a[key],b[key])
 elif isinstance(a,(int,float)):assert abs(a-b)<1e-12,(a,b)
 else:assert a==b,(a,b)
count=0
for name,state,questions,images in cases():
 items=p.prepare(state,questions,images)
 for item in items:
  qid=item['question_id'];baseline=refs['bf16'][name]['details'][qid]
  assert hashlib.sha256(json.dumps([item['input_ids']]).encode()).hexdigest()==baseline['input_ids_sha256']
  grid=item['image_features'].get('image_grid_thw')
  assert (grid.tolist() if grid is not None else None)==baseline['image_grid_thw']
  for mode,ref in refs.items():compare(p.finish(item,ref[name]['details'][qid]['candidate_logits']),ref[name]['answers'][qid])
  count+=1
 result.append(name)
for bad in [[float('nan'),0],[float('inf'),0],[0]]:
 try:decode_answer('choice',{'a':'A','b':'B'},bad)
 except ValueError:pass
 else:raise AssertionError('invalid logits accepted')
# The processor must not load an inference library or a model implementation.
assert not any('libjev_runner' in s or 'libllama' in s for s in Path('/proc/self/maps').read_text().splitlines()) if Path('/proc/self/maps').exists() else True
print(json.dumps({'complete':True,'cases':len(result),'questions':count,'reference_modes':list(refs),'input_tokens_and_image_grids_match':True,'postprocessing_matches':True,'model_loaded':False},indent=2))

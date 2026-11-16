"""Build the external reference adapter against a user's own llama.cpp build."""
import argparse,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,default=Path(__file__).with_name('libjev_runner.so'));a=p.parse_args()
s=a.source.resolve();lib=(a.build/'bin').resolve();out=a.output.resolve()
for f in [s/'include/llama.h',s/'tools/mtmd/mtmd.h',lib/'libllama.so',lib/'libmtmd.so']:
 if not f.exists():p.error(f'Missing dependency: {f}')
out.parent.mkdir(parents=True,exist_ok=True)
subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2','-fPIC','-shared',str(Path(__file__).with_name('runner.cpp')),
 '-I'+str(s/'include'),'-I'+str(s/'ggml/include'),'-I'+str(s/'tools/mtmd'),'-L'+str(lib),'-Wl,-rpath,'+str(lib),
 '-lllama','-lmtmd','-lggml','-lggml-base','-o',str(out)],check=True)
print(out)

#!/usr/bin/env python3
"""Build the overlay from an initialized pinned client checkout without altering it."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

def main():
    base=Path(__file__).resolve().parent;repo=base.parent;p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=repo.parent/'cs16-client');p.add_argument('--work',type=Path,default=repo/'.lab/rebuild');p.add_argument('--jobs',type=int,default=8)
    a=p.parse_args();source=a.source.resolve();work=a.work.resolve();copy=work/'source';build=work/'build'
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!='6a49bcc6f5292dec13046b23140c1e555dca8b31':raise SystemExit('Source revision differs from the pinned classroom client.')
    if not (source/'3rdparty/mainui_cpp/miniutl').is_dir():raise SystemExit('Initialize source submodules first.')
    if not copy.exists():shutil.copytree(source,copy,symlinks=True,ignore=shutil.ignore_patterns('.git','build','*.o','*.pdb'))
    subprocess.run([sys.executable,str(base/'tools/apply_source.py'),str(copy)],check=True)
    subprocess.run(['cmake','-S',str(copy),'-B',str(build),'-DCMAKE_BUILD_TYPE=RelWithDebInfo','-DBUILD_SERVER=OFF','-DBUILD_MAINUI=OFF'],check=True)
    subprocess.run(['cmake','--build',str(build),'--parallel',str(a.jobs)],check=True)
    dist=base/'dist';dist.mkdir(exist_ok=True);library=dist/'client_amd64.so';shutil.copy2(build/'cl_dll/client_amd64.so',library)
    sys.path.insert(0,str(base/'tools'));from patch_clip import inspect
    manifest=base/'patches/clip-manifest.json';known=json.loads(manifest.read_text());metadata=inspect(library);metadata['build']='Local classroom rebuild'
    known=[m for m in known if m['sha256']!=metadata['sha256']];known.append(metadata);manifest.write_text(json.dumps(known,indent=2)+'\n')
    print('Overlay built:',library)

if __name__=='__main__':main()

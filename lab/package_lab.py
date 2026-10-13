#!/usr/bin/env python3
"""Package the student overlay, source, tools, documentation, and evidence."""
import hashlib
import json
from pathlib import Path
import tarfile
import datetime

PRIVATE_PLAN_NAMES = {'lecture.md', 'demo-card.md'}

def main():
    lab=Path(__file__).resolve().parent;repo=lab.parent;dist=lab/'dist';dist.mkdir(exist_ok=True)
    library=dist/'client_amd64.so'
    if not library.exists():raise SystemExit('Build the client library first.')
    meta={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':'Linux x86-64; glibc >= 2.38','client_commit':'6a49bcc6f5292dec13046b23140c1e555dca8b31','engine_commit':'fd0cd6afdda9dff94346af60884b99876001ca5f','gamedll_commit':'7be9d59dca1ee11d270e4631d7e3be0c67a1a82b','client_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),'server':'cs.mahaloz.re:27015','all_source_cheats_default_off':True,'game_assets_included':False}
    (dist/'BUILD-INFO.json').write_text(json.dumps(meta,indent=2)+'\n')
    archive=dist/'hackpack-overlay-linux-x86_64.tar.gz'
    with tarfile.open(archive,'w:gz') as output:
        for root in [lab,repo/'server']:
            output.add(root,arcname=str(root.relative_to(repo)),recursive=False)
            for path in sorted(root.rglob('*')):
                if '__pycache__' in path.parts or path==archive or path.name=='SHA256SUMS.txt' or path.name in PRIVATE_PLAN_NAMES:continue
                output.add(path,arcname=str(path.relative_to(repo)),recursive=False)
        output.add(repo/'README.md',arcname='README.md')
    files=[library,archive]
    (dist/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in files)+'\n')
    print(archive,'bytes',archive.stat().st_size)

if __name__=='__main__':main()

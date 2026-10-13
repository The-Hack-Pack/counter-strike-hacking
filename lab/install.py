#!/usr/bin/env python3
"""Install or remove the lab overlay in an extracted Linux portable client."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
KEYS = tuple('F'+str(i) for i in range(5,12))
def binding_key(line):
    try:words=shlex.split(line)
    except ValueError:return None
    if len(words)>=2 and words[0].lower() in ('bind','unbind') and words[1].upper() in KEYS:return words[1].upper()
    return None
def bindings(config):
    result={key:'unbind '+key for key in KEYS}
    if config.exists():
        for line in config.read_text().splitlines():
            key=binding_key(line)
            if key:result[key]=line
    return result
def restore_bindings(config,saved):
    # Keep settings changed by the student while the lab was installed.
    lines=config.read_text().splitlines() if config.exists() else []
    lines=[line for line in lines if binding_key(line) is None]
    lines.extend(saved[key] for key in KEYS)
    config.write_text('\n'.join(lines)+'\n')
def active(runtime):
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if (p/'cwd').resolve()==runtime and b'xash3d' in (p/'cmdline').read_bytes():return p.name
        except (OSError,RuntimeError):pass
    return None
def replace(source,target):
    fd,temp=tempfile.mkstemp(prefix=target.name+'.',dir=target.parent);os.close(fd)
    try:shutil.copy2(source,temp);os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def main():
    base=Path(__file__).resolve().parent;p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runtime',type=Path);p.add_argument('--library',type=Path,default=base/'dist/client_amd64.so');p.add_argument('--undo',action='store_true');a=p.parse_args()
    runtime=a.runtime.resolve();target=runtime/'cstrike/cl_dlls/client_amd64.so';backup=Path(str(target)+'.hackpack-original');receipt=runtime/'hackpack-install.json'
    if active(runtime):raise SystemExit('Quit this runtime before changing its library.')
    if not target.exists() or not (runtime/'start.sh').exists():raise SystemExit('Expected the extracted Linux portable runtime.')
    if a.undo:
        if not backup.exists() or not receipt.exists():raise SystemExit('No saved lab installation found.')
        metadata=json.loads(receipt.read_text())
        if sha(backup)!=metadata['original_sha256']:raise SystemExit('Original backup hash changed.')
        if sha(target)!=metadata['installed_sha256']:raise SystemExit('Library changed after installation. Undo the clip patch first.')
        replace(backup,target)
        if 'previous_function_keys' in metadata:restore_bindings(runtime/'cstrike/config.cfg',metadata['previous_function_keys'])
        backup.unlink();receipt.unlink();(runtime/'cstrike/hackpack.cfg').unlink(missing_ok=True)
        print('Original client restored:',target);return
    if not a.library.exists():raise SystemExit('Build the overlay first with lab/build_lab.py.')
    if backup.exists():raise SystemExit('Overlay already installed. Uninstall it before installing a new build.')
    shutil.copy2(target,backup);original=sha(backup);replace(a.library,target)
    shutil.copy2(base/'hackpack.cfg',runtime/'cstrike/hackpack.cfg')
    receipt.write_text(json.dumps({'original_sha256':original,'installed_sha256':sha(target),'previous_function_keys':bindings(runtime/'cstrike/config.cfg')},indent=2)+'\n')
    print('Installed. Launch with lab/launch.py, or add +exec hackpack.cfg to start.sh.')

if __name__=='__main__':main()

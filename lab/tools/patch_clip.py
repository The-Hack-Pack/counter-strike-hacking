#!/usr/bin/env python3
"""Patch the pinned x86-64 CurWeapon parser to display 99; verify and undo safely."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import os
import struct

BEFORE=bytes.fromhex('0f be 51 02 89 d6')
AFTER=bytes.fromhex('ba 63 00 00 00 90')  # mov edx,99; nop (same six bytes)
MANIFEST=Path(__file__).resolve().parents[1]/'patches/clip-manifest.json'

def digest(data):return hashlib.sha256(data).hexdigest()

def mapped_pids(path):
    target=str(path.resolve());result=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            for line in (process/'maps').read_text().splitlines():
                fields=line.split(maxsplit=5)
                if len(fields)==6 and fields[5].removesuffix(' (deleted)')==target:
                    result.append(process.name);break
        except OSError:pass
    return result

def inspect(path):
    data=path.read_bytes()
    if not data.startswith(b'\x7fELF\x02\x01'):raise ValueError('Expected little-endian ELF64')
    # Resolve the exported C++ method through ELF64 .dynsym. Do not patch a
    # coincidentally matching instruction sequence in another function.
    section_offset=struct.unpack_from('<Q',data,40)[0]
    entry_size,section_count=struct.unpack_from('<HH',data,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,section_offset+i*entry_size) for i in range(section_count)]
    functions=[]
    for section in sections:
        if section[1]!=11:continue # SHT_DYNSYM
        strings=sections[section[6]];names=data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,offset)
            symbol=names[name:].split(b'\0',1)[0]
            if b'CHudAmmo' in symbol and b'MsgFunc_CurWeapon' in symbol and size:
                region=sections[index];start=region[4]+value-region[3];functions.append((start,size))
    if len(functions)!=1:raise ValueError('Expected one exported CurWeapon parser')
    start,size=functions[0];code=data[start:start+size]
    offsets=[];offset=code.find(BEFORE)
    while offset!=-1:offsets.append(start+offset);offset=code.find(BEFORE,offset+1)
    if len(offsets)!=1:raise ValueError(f'Expected exactly one verified parser signature, found {len(offsets)}')
    return {'sha256':digest(data),'offset':offsets[0],'before':BEFORE.hex(),'after':AFTER.hex()}

def patch(path,undo=False):
    running=mapped_pids(path)
    if running:raise ValueError('Quit clients mapping this library before patching: PID '+', '.join(running))
    backup=Path(str(path)+'.clip-original')
    if undo:
        if not backup.exists():raise ValueError('No clip backup exists')
        original=backup.read_bytes();meta=inspect(backup)
        expected=original[:meta['offset']]+AFTER+original[meta['offset']+6:]
        if path.read_bytes()!=expected:raise ValueError('Current binary changed since patching; refusing to overwrite it')
        shutil.copy2(backup,path);backup.unlink();return {'restored_sha256':digest(original)}
    data=path.read_bytes();known=json.loads(MANIFEST.read_text())
    meta=next((x for x in known if x['sha256']==digest(data)),None)
    if not meta:raise ValueError('Binary hash is not in the tested manifest. Rebuild with build_lab.py to register your build.')
    offset=meta['offset']
    if data[offset:offset+6]!=BEFORE:raise ValueError('Original instruction bytes do not match')
    if backup.exists():raise ValueError('Backup already exists; undo the previous patch first')
    shutil.copy2(path,backup)
    changed=data[:offset]+AFTER+data[offset+6:]
    fd,temp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(changed)
        shutil.copymode(path,temp);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {**meta,'patched_sha256':digest(changed),'backup':str(backup)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('library',type=Path);p.add_argument('--undo',action='store_true')
    a=p.parse_args()
    try:print(json.dumps(patch(a.library,a.undo),indent=2))
    except (ValueError,OSError) as e:raise SystemExit(str(e))

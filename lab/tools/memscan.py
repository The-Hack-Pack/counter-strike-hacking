#!/usr/bin/env python3
"""Small Linux memory scanner for the class's own running game process.

Examples in the prompt: scan int 30; scan int 29; list; write 0xADDRESS int 99.
Launch as parent with --launch RUNTIME/start.sh ... when Yama blocks attachment.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import time

FORMATS = {'int': '<i', 'float': '<f', 'double': '<d', 'byte': '<B'}

class Memory:
    def __init__(self, pid, module=None):
        self.pid = pid
        self.module = module
        self.fd = os.open(f'/proc/{pid}/mem', os.O_RDWR)
        self.candidates = None
        self.kind = None
        self.history = []

    def maps(self):
        previous_end=0;previous_selected=False
        for line in Path(f'/proc/{self.pid}/maps').read_text().splitlines():
            fields=line.split(maxsplit=5)
            lo,hi=(int(x,16) for x in fields[0].split('-'))
            name=fields[5] if len(fields)>5 else '[anonymous]'
            selected=not self.module or self.module in name or (previous_selected and lo==previous_end and name=='[anonymous]')
            previous_end=hi;previous_selected=selected
            if selected and 'r' in fields[1] and 'w' in fields[1]:yield lo,hi,name

    def read(self, address, kind):
        fmt=FORMATS[kind]
        return struct.unpack(fmt,os.pread(self.fd,struct.calcsize(fmt),address))[0]

    def scan(self, kind, value):
        if self.kind is not None and kind!=self.kind:
            raise ValueError('Use reset before changing the value type.')
        self.kind=kind;fmt=FORMATS[kind];value=float(value) if kind in ('float','double') else int(value,0) if isinstance(value,str) else int(value)
        packed=struct.pack(fmt,value);size=len(packed);found=[]
        if self.candidates is None:
            for lo,hi,name in self.maps():
                for start in range(lo,hi,4*1024*1024):
                    try:data=os.pread(self.fd,min(4*1024*1024,hi-start),start)
                    except OSError:continue
                    pos=data.find(packed)
                    while pos!=-1:
                        if (start+pos)%size==0: found.append(start+pos)
                        pos=data.find(packed,pos+1)
        else:
            for address in self.candidates:
                try:
                    if os.pread(self.fd,size,address)==packed:found.append(address)
                except OSError:pass
        self.candidates=found
        result={'type':kind,'value':value,'count':len(found),'addresses':[hex(x) for x in found]}
        self.history.append(result)
        return result

    def write(self,address,kind,value):
        fmt=FORMATS[kind];value=float(value) if kind in ('float','double') else int(value,0) if isinstance(value,str) else int(value)
        before=self.read(address,kind);data=struct.pack(fmt,value)
        # Require an explicitly selected mapped writable address; never patch all matches.
        if not any(lo<=address and address+len(data)<=hi for lo,hi,_ in self.maps()):
            raise ValueError('Address is not inside a writable mapping.')
        if os.pwrite(self.fd,data,address)!=len(data):raise OSError('Short write')
        return {'address':hex(address),'before':before,'after':self.read(address,kind)}

    def describe(self,address):
        for lo,hi,name in self.maps():
            if lo<=address<hi:return f'{name}+0x{address-lo:x}'
        return 'unmapped'

    def close(self):os.close(self.fd)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int);p.add_argument('--module',help='Restrict to a module and its contiguous anonymous BSS mapping.');p.add_argument('--launch',nargs=argparse.REMAINDER)
    a=p.parse_args();child=None
    if bool(a.pid)==bool(a.launch):p.error('Choose --pid or --launch.')
    if a.launch:
        child=subprocess.Popen(a.launch,stdout=open('memscan-game.log','w'),stderr=subprocess.STDOUT)
        a.pid=child.pid
        print(f'Launched PID {a.pid}. Game output: memscan-game.log')
        time.sleep(1)
    try:memory=Memory(a.pid,a.module)
    except PermissionError:
        raise SystemExit('Linux ptrace policy blocked access. Use --launch, or the lab launcher with its explicit debug opt-in.')
    print('Commands: scan TYPE VALUE | list | read ADDRESS TYPE | write ADDRESS TYPE VALUE | save FILE | reset | quit')
    try:
        while True:
            try:args=shlex.split(input('scan> '))
            except (EOFError,KeyboardInterrupt):break
            if not args:continue
            try:
                command=args[0]
                if command=='quit':break
                elif command=='reset':memory.candidates=None;memory.kind=None;memory.history=[]
                elif command=='scan':
                    result=memory.scan(args[1],args[2]);print(f"{result['count']} candidates")
                    if result['count']<=20:print(' '.join(result['addresses']))
                elif command=='list':
                    for address in (memory.candidates or [])[:100]:print(hex(address),memory.describe(address),memory.read(address,memory.kind))
                elif command=='read':print(memory.read(int(args[1],0),args[2]))
                elif command=='write':print(json.dumps(memory.write(int(args[1],0),args[2],args[3])))
                elif command=='save':Path(args[1]).write_text(json.dumps({'pid':a.pid,'history':memory.history},indent=2)+'\n')
                else:print('Unknown command')
            except (ValueError,KeyError,IndexError,OSError) as e:print(e)
    finally:
        memory.close()
        if child and child.poll() is None:child.terminate()

if __name__=='__main__':main()

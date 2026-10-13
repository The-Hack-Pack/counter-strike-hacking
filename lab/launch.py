#!/usr/bin/env python3
"""Launch a lab runtime, then connect after its startup menu has initialized."""
import argparse
import fcntl
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runtime',type=Path);p.add_argument('--server',default='cs.mahaloz.re:27015');p.add_argument('--port',type=int,default=49100)
    p.add_argument('--name',default='HackPack-Instructor');p.add_argument('--team',choices=['t','ct']);p.add_argument('--debug',action='store_true')
    a,extra=p.parse_known_args();runtime=a.runtime.resolve()
    env=dict(os.environ)
    if a.debug:env['HACKPACK_ALLOW_PTRACE']='1'
    # Upstream qport uses a time-seeded PRNG. Serialize same-user local launches across seconds.
    lock=open(Path(tempfile.gettempdir())/f'hackpack-launch-{os.getuid()}.lock','a+')
    fcntl.flock(lock,fcntl.LOCK_EX);lock.seek(0)
    prior=lock.read().strip();delay=2-(time.time()-float(prior)) if prior else 0
    if delay>0:time.sleep(delay)
    command=[str(runtime/'start.sh'),'+name',a.name,'+exec','hackpack.cfg','+hp_bridge_port',str(a.port)]
    if a.team:command+=['+hp_autojoin','1' if a.team=='t' else '2']
    command+=extra[1:] if extra and extra[0]=='--' else extra
    child=subprocess.Popen(command,cwd=runtime,env=env)
    lock.seek(0);lock.truncate();lock.write(str(time.time()));lock.flush();fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    time.sleep(2)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.sendto(('CMD1 connect '+a.server+'\n').encode(),('127.0.0.1',a.port))
    try:return child.wait()
    except KeyboardInterrupt:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.sendto(b'CMD1 hp_off\nquit\n',('127.0.0.1',a.port))
        try:child.wait(timeout=3)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        return 0

if __name__=='__main__':raise SystemExit(main())

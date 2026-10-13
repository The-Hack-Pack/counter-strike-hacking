#!/usr/bin/env python3
"""Send server-console commands through Docker's attached TTY (no RCON)."""
import argparse
import os
import pty
import select
import subprocess
import time
import shlex
from pathlib import Path

def console(command, container='counter-strike-server-1', wait=0.4):
    master, slave = pty.openpty()
    process = subprocess.Popen(['docker', 'attach', '--sig-proxy=false', container],
                               stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    try:
        time.sleep(0.15)
        os.write(master, (command.rstrip() + '\n').encode())
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                try: output.extend(os.read(master, 65536))
                except OSError: break
    finally:
        # SIGKILL affects only the local attach CLI; --sig-proxy=false protects the server.
        process.kill()
        process.wait(timeout=3)
        os.close(master)
    return output.decode(errors='replace')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', help='Quote a command, or several newline-separated commands.')
    p.add_argument('--container', default='counter-strike-server-1')
    p.add_argument('--wait', type=float, default=0.4)
    p.add_argument('--ssh', help='Run the console helper on an existing SSH server profile.')
    p.add_argument('--remote-repo', default='/home/mahaloz/github/counter-strike-hacking')
    p.add_argument('--known-hosts', type=Path)
    a = p.parse_args()
    if a.ssh:
        args=['ssh','-x','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes']
        if a.known_hosts:args+=['-o','UserKnownHostsFile='+str(a.known_hosts.resolve())]
        remote=shlex.join(['python3',a.remote_repo+'/lab/tools/server_console.py',a.command,'--container',a.container,'--wait',str(a.wait)])
        subprocess.run(args+[a.ssh,remote],check=True)
    else:print(console(a.command, a.container, a.wait), end='')

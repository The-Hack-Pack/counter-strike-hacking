#!/usr/bin/env python3
"""Display the information a lab client already received; no server-console access."""
import argparse
import json
from pathlib import Path
import socket

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=49100);p.add_argument('--count',type=int,default=1);p.add_argument('--record',type=Path);a=p.parse_args()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1',a.port+1));sock.settimeout(10)
        for _ in range(a.count):
            data=sock.recv(65535);state=json.loads(data);print(json.dumps(state,indent=2))
            if a.record:a.record.write_text(json.dumps(state,indent=2)+'\n')

if __name__=='__main__':main()

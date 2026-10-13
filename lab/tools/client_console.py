#!/usr/bin/env python3
"""Send a local command to a running lab client's optional loopback bridge."""
import argparse
import socket

def send(command, port=49100):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(('CMD1 '+command.rstrip()+'\n').encode(), ('127.0.0.1',port))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command');p.add_argument('--port',type=int,default=49100)
    a=p.parse_args();send(a.command,a.port)

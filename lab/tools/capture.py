#!/usr/bin/env python3
"""Capture an unedited in-game X11 screenshot as PNG (requires xwd and Pillow)."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from PIL import Image

def capture(output,display):
    with tempfile.TemporaryDirectory(prefix='hackpack-shot-') as work:
        raw=Path(work)/'screen.xwd'
        subprocess.run(['xwd','-root','-silent','-out',str(raw)],env=dict(os.environ,DISPLAY=display),check=True)
        data=raw.read_bytes();h=struct.unpack('>25I',data[:100])
        if h[11]!=32 or h[7]!=0:raise ValueError('Expected the tested Xvfb little-endian 32-bit pixel layout')
        pixels=data[h[0]+12*h[19]:]
        image=Image.frombytes('RGB',(h[4],h[5]),pixels,'raw','BGRX',h[12])
        Path(output).parent.mkdir(parents=True,exist_ok=True);image.save(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--display',default=os.getenv('DISPLAY',':93'));a=p.parse_args();capture(a.output,a.display)

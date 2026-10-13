#!/usr/bin/env python3
"""Decode a pinned YaPB v2 graph into inspectable JSON waypoints for Python A*."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def ulz_decode(data, expected):
    # YaPB/crlib ULZ format. Checked bounds keep corrupt graphs from allocating arbitrary data.
    if not 0 < expected <= 4096*220:raise ValueError('Unsupported graph size')
    output=bytearray();cursor=0
    def varint():
        nonlocal cursor
        value=0
        for shift in range(0,22,7):
            if cursor>=len(data):raise ValueError('Truncated ULZ integer')
            byte=data[cursor];cursor+=1;value+=byte<<shift
            if byte<128:return value
        return value
    while cursor<len(data):
        token=data[cursor];cursor+=1
        if token>=32:
            run=token>>5
            if run==7:run+=varint()
            if cursor+run>len(data) or len(output)+run>expected:raise ValueError('Invalid ULZ literal')
            output.extend(data[cursor:cursor+run]);cursor+=run
            if cursor>=len(data):break
        length=(token&15)+4
        if length==19:length+=varint()
        if cursor+2>len(data):raise ValueError('Truncated ULZ match')
        distance=((token&16)<<12)+struct.unpack_from('<H',data,cursor)[0];cursor+=2
        if not 1<=distance<=len(output) or len(output)+length>expected:raise ValueError('Invalid ULZ match')
        for _ in range(length):output.append(output[-distance])
    if len(output)!=expected:raise ValueError('Unexpected decompressed graph size')
    return bytes(output)

def decode(path):
    data=path.read_bytes();magic,version,options,count,compressed,uncompressed=struct.unpack_from('<6i',data)
    if magic!=0x59415042 or version!=2 or not 1<=count<=4096 or uncompressed!=count*220:
        raise ValueError('Expected a YaPB v2 graph with 220-byte Path records')
    raw=ulz_decode(data[24:24+compressed],uncompressed);nodes=[]
    for i in range(count):
        offset=i*220;number,flags=struct.unpack_from('<ii',raw,offset)
        if number!=i:raise ValueError('Non-contiguous graph indices')
        links=[]
        for j in range(8):
            distance,linkflags,index=struct.unpack_from('<iHh',raw,offset+56+j*20+12)
            if index>=0:
                if index>=count:raise ValueError('Invalid graph link')
                links.append({'to':index,'jump':bool(linkflags&1),'distance':distance})
        nodes.append({'id':i,'flags':flags,'origin':list(struct.unpack_from('<3f',raw,offset+8)),'links':links})
    author=data[24+compressed:24+compressed+32].split(b'\0')[0].decode(errors='replace')
    return {'format':'Hack Pack waypoints v1','source':'YaPB de_dust2.graph (v2)','source_sha256':hashlib.sha256(data).hexdigest(),'author':author,'nodes':nodes}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('graph',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=decode(a.graph);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(f"Exported {len(result['nodes'])} nodes; author {result['author']}")

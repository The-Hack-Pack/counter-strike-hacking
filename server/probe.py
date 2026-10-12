#!/usr/bin/env python3
"""Probe Xash3D discovery and protocol-49 connection admission over UDP."""

import argparse
import json
import re
import secrets
import socket
import sys

OOB = b"\xff\xff\xff\xff"


def exchange(sock, request):
    sock.send(OOB + request)
    packet = sock.recv(65535)
    if not packet.startswith(OOB):
        raise ValueError(f"Unexpected non-OOB response: {packet[:100]!r}")
    return packet[4:].rstrip(b"\x00\n").decode("utf-8", errors="replace")


def probe(host, port, timeout, query_only):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        reply = exchange(sock, b"info 49\n")
        if not reply.startswith("info\n"):
            raise ValueError(f"Unexpected discovery response: {reply!r}")
        fields = reply.split("\n", 1)[1].lstrip("\\").split("\\")
        info = dict(zip(fields[::2], fields[1::2]))
        if info.get("gamedir") != "cstrike" and info.get("g") != "cstrike":
            raise ValueError(f"Expected Counter-Strike, received: {info!r}")
        result = {"address": f"{sock.getpeername()[0]}:{port}", "info": info}
        if not query_only:
            reply = exchange(sock, b"getchallenge\n")
            match = re.match(r"(?:challenge|A00000000)\s+(-?\d+)", reply)
            if not match:
                raise ValueError(f"Unexpected challenge response: {reply!r}")
            challenge = match.group(1)
            qport = secrets.randbelow(65535) + 1
            protinfo = f"\\uuid\\{secrets.token_hex(16)}\\qport\\{qport}\\ext\\0\\d\\2"
            userinfo = "\\name\\connectivity-probe\\rate\\25000\\cl_updaterate\\20"
            request = f'connect 49 {challenge} "{protinfo}" "{userinfo}"\n'
            reply = exchange(sock, request.encode())
            if not reply.startswith("client_connect"):
                raise ValueError(f"Connection rejected: {reply!r}")
            result["connection"] = "accepted (protocol 49)"
            # A connectionless probe does not enter the map. Its slot expires
            # after sv_timeout; health checks use --query-only to avoid slots.
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=27015)
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--query-only", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.host, args.port, args.timeout, args.query_only), indent=2))
    except (OSError, ValueError) as error:
        print(f"FAIL {args.host}:{args.port}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Launch a Linux lab runtime or macOS CS16Client.app and connect to a server."""
import argparse
import fcntl
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import tempfile
import time


def launch_command(runtime, args, extra):
    """Return the command, working directory, and whether it uses the lab bridge."""
    if runtime.suffix.lower() == '.app':
        if sys.platform != 'darwin':
            raise ValueError('A macOS .app bundle must be launched on macOS.')
        contents = runtime / 'Contents'
        try:
            with (contents / 'Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
        except (OSError, ValueError) as error:
            raise ValueError('Could not read the app bundle Info.plist: ' + str(error)) from error
        executable = info.get('CFBundleExecutable') if isinstance(info, dict) else None
        if not isinstance(executable, str) or not executable or Path(executable).name != executable:
            raise ValueError('The app bundle has no valid CFBundleExecutable.')
        entrypoint = contents / 'MacOS' / executable
        working = contents / 'Resources' / 'Runtime'
        if not entrypoint.is_file() or not os.access(entrypoint, os.X_OK) or not working.is_dir():
            raise ValueError('Expected CS16Client.app with an executable and Contents/Resources/Runtime.')
        if args.team:
            raise ValueError('--team requires the Linux lab overlay; choose a team in the macOS game menu.')
        # The native app sets up its read-only assets and writable user directory.
        # The stock macOS client has no lab bridge; use the engine startup queue.
        return [str(entrypoint), '+name', args.name, *extra, '+connect', args.server], working, False

    if sys.platform == 'darwin':
        raise ValueError('On macOS, pass the path to CS16Client.app instead of the Linux runtime.')
    entrypoint = runtime / 'start.sh'
    if not entrypoint.is_file() or not os.access(entrypoint, os.X_OK):
        raise ValueError('Expected a Linux portable runtime with an executable start.sh.')
    command = [str(entrypoint), '+name', args.name, '+exec', 'hackpack.cfg',
               '+hp_bridge_port', str(args.port)]
    if args.team:
        command += ['+hp_autojoin', '1' if args.team == 't' else '2']
    return command + extra, runtime, True


def start_serialized(command, working, env):
    # Upstream qport uses a time-seeded PRNG. Serialize same-user local launches across seconds.
    lock_path = Path(tempfile.gettempdir()) / f'hackpack-launch-{os.getuid()}.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lock.seek(0)
        prior = lock.read().strip()
        delay = 2 - (time.time() - float(prior)) if prior else 0
        if delay > 0:
            time.sleep(delay)
        # Keep terminal Ctrl-C in the launcher so it can shut down the game cleanly.
        child = subprocess.Popen(command, cwd=working, env=env, start_new_session=True)
        lock.seek(0)
        lock.truncate()
        lock.write(str(time.time()))
        lock.flush()
    return child


def send_command(command, port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(('CMD1 ' + command + '\n').encode(), ('127.0.0.1', port))


def stop_client(child, port, bridge):
    if child.poll() is not None:
        return
    if bridge:
        send_command('hp_off\nquit', port)
    else:
        child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path, help='Linux runtime directory or macOS CS16Client.app')
    parser.add_argument('--server', default='cs.mahaloz.re:27015')
    parser.add_argument('--port', type=int, default=49100, help='Linux lab bridge port (default: 49100)')
    parser.add_argument('--name', default='HackPack-Instructor')
    parser.add_argument('--team', choices=['t', 'ct'], help='Auto-select a team with the Linux lab overlay')
    parser.add_argument('--debug', action='store_true', help='Allow Linux ptrace attachment; no effect on macOS')
    args, extra = parser.parse_known_args(argv)
    if extra and extra[0] == '--':
        extra = extra[1:]
    try:
        command, working, bridge = launch_command(args.runtime.expanduser().resolve(), args, extra)
    except ValueError as error:
        parser.error(str(error))
    env = dict(os.environ)
    if args.debug and bridge:
        env['HACKPACK_ALLOW_PTRACE'] = '1'
    child = None
    try:
        child = start_serialized(command, working, env)
        if bridge:
            time.sleep(2)
            if child.poll() is None:
                send_command('connect ' + args.server, args.port)
        return child.wait()
    except KeyboardInterrupt:
        if child is None:
            return 130
        stop_client(child, args.port, bridge)
        return 0
    except OSError as error:
        if child is not None:
            stop_client(child, args.port, bridge)
        parser.exit(1, f'Could not launch client: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())

# Hack Pack client lab

The overlay adds optional wall boxes, a custom radar, head aiming, jump
automation, simulation-speed controls, and a local observation/action bridge
to the supplied Linux CS16Client. All source features start off. This is
Counter-Strike 1.6 on Xash3D protocol 49.

## Install and connect

Use a writable copy of the supplied Linux x86-64 game runtime. It requires glibc
2.38 or newer and the graphics support needed by that runtime. Python 3 runs the
helpers. The overlay archive does not include game assets or the native engine.
Extract `lab/dist/hackpack-overlay-linux-x86_64.tar.gz` and run from its root:

```bash
python3 lab/install.py /path/to/CS16Client-Linux-x86_64
python3 lab/launch.py /path/to/CS16Client-Linux-x86_64 --server cs.mahaloz.re:27015 --name Student --debug
```

The installer saves the original library and function-key bindings. The
launcher connects after the startup menu initializes. `--debug` allows a
same-user debugger or memory scanner to attach to this process. Use `--team t`
or `--team ct` to select a team automatically. Additional clients on one
machine need distinct bridge ports, such as `--port 49200`.

## Controls

Open the game console with the backtick key.

| Key | Action |
|---|---|
| F5 | Toggle wall boxes |
| F6 | Toggle radar |
| F7 | Toggle head aiming while attack is held |
| F8 | Toggle repeated jumping while jump is held |
| F9 | Cycle simulation speed through 1×, 2×, 3× |
| F10 | Clear source features and restore speed to 1× |
| F11 | Print client state and memory addresses |

Console variables include `hp_esp`, `hp_radar`, `hp_aim`, `hp_autofire`,
`hp_bhop`, and `hp_speed`. Terminal control uses the optional local bridge:

```bash
python3 lab/tools/client_console.py 'hp_esp 1; hp_radar 1'
python3 lab/tools/watch_state.py --port 49100 --count 1
```

Telemetry contains local state and received player observations, including
position, age, freshness, visibility, and the head-position source. Stock PVS
limits distant-player replication; the radar distinguishes current and cached
observations. Server operators can configure deliberate all-map replication
with `hp_full_visibility`. See [server configuration](../server/README.md).
Head targeting is subject to spread, movement, latency, and pose accuracy.

## Memory and binary tools

Find the game PID with `pgrep -af xash3d`. The scanner accepts `scan TYPE VALUE`,
`list`, `read ADDRESS TYPE`, `write ADDRESS TYPE VALUE`, `save FILE`, and `reset`.
Supported types are `int`, `float`, `double`, and `byte`.

```bash
python3 lab/tools/memscan.py --pid GAME_PID
python3 lab/tools/memscan.py --pid GAME_PID --module libxash.so
```

Module filtering includes contiguous anonymous BSS. Writes require a selected
writable address. Addresses vary across runs.

Quit the game before applying the separate clip-display instruction patch:

```bash
python3 lab/tools/patch_clip.py /path/to/runtime/cstrike/cl_dlls/client_amd64.so
```

The patcher verifies the whole library hash and expected instruction bytes,
retains a backup, and refuses unknown builds or a currently mapped library.
This changes the local clip display; server ammo remains authoritative.

## Python controller

Install the overlay into a separate runtime for the bot:

```bash
python3 lab/bot.py --runtime /path/to/bot-runtime --server cs.mahaloz.re:27015 --team t --seconds 60 --record bot.jsonl
```

Python chooses movement, searches the Dust2 waypoint graph with A*, selects
opponents, and aims/fires. The native engine provides network transport,
prediction, and animated pose data. Add `--headless` for Xvfb and software
OpenGL, or use the normal window. Ctrl-C cleans up the bot; external actions
expire after 250 ms without updates. The supplied graph is specific to Dust2,
and navigation is approximate. Avoid running another telemetry receiver on the
bot's port while its controller is active.

## Build and package

The builder uses an initialized checkout at the pinned client revision and
creates a separate source/build copy:

```bash
python3 lab/build_lab.py --source /path/to/cs16-client
python3 lab/package_lab.py
```

See [the source module](client/hackpack_lab.cpp),
[hook applicator](tools/apply_source.py), [Python bot](bot.py), and
[patch manifest](patches/clip-manifest.json). Build metadata, licenses, and
checksums accompany the generated library/archive in `lab/dist/`.
Third-party notices are included for [CS16Client](licenses/CS16Client.txt),
[miniutl](licenses/miniutl.txt), and [YaPB](licenses/YaPB.txt).
[Verification evidence](evidence/README.md) includes screenshots and raw logs.

## Turn off and uninstall

F10 or `hp_off` clears source features. The persistent clip patch needs its own
undo after quitting; run the first command only if that patch was applied:

```bash
python3 lab/tools/patch_clip.py /path/to/runtime/cstrike/cl_dlls/client_amd64.so --undo
python3 lab/install.py /path/to/runtime --undo
```

Uninstall verifies and restores the original library and prior F5–F11 bindings
while retaining other changed settings. After uninstalling, launch with the
runtime's original `start.sh` and connect from its normal console.

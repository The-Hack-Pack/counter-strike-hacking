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

### macOS native client

The same launcher accepts the supplied `CS16Client.app` on macOS. Run from the
repository root, adjusting the app path if you moved it to Applications:

```bash
python3 lab/launch.py ../CS16Client.app --server cs.mahaloz.re:27015 --name Student
# Forward engine options after --, for example:
python3 lab/launch.py /Applications/CS16Client.app --name Student -- -width 1280 -height 800
```

The launcher runs the bundle's native executable and queues the connection with
the engine. The app handles its bundled libraries and assets; settings,
downloads, `launcher.log`, and `engine.log` live in
`~/Library/Application Support/CS16Client/`. The app also accepts an absolute
`CS16CLIENT_USERDIR` environment override for a separate settings directory.
Ctrl-C in the launcher terminal stops the client.

The supplied macOS app is the stock native client. The Linux overlay archive
and installer cannot be installed into it. Select a team in the game menu;
`--team` is rejected for this client. F5–F11 lab features, Python bot control,
and the UDP bridge require the Linux lab overlay. `--port` and `--debug` only
apply to Linux launches.

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

For an interactive search inside GDB or GEF, pause the game and source
[gdb_ammo.py](tools/gdb_ammo.py), using its absolute path if GDB's working
directory differs from the repository root:

```gdb
source lab/tools/gdb_ammo.py
ammo-scan 20
```

The command scans writable memory for aligned 32-bit integers containing 20,
saves every candidate address, and resumes the game. Fire one shot, then Ctrl-C
in the GDB terminal: it filters the same addresses for 19. Press Enter at the
scanner prompt to resume and repeat for 18, 17, and so on; enter `q` to finish
with the game paused and results retained. A numeric response retries the saved
candidates at that actual clip count if you fired extra shots. A failed filter
keeps the preceding candidates. Other breakpoints/signals return control to GDB.

```gdb
ammo-list 0
ammo-save /tmp/ammo-search.json
```

`ammo-run` resumes an existing search, and `ammo-refine VALUE` filters it once
without resuming. An optional module argument narrows the initial search:
`ammo-scan 20 client_amd64.so`, including its adjacent anonymous BSS. The script
uses GDB's memory API and does not modify game memory.

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
python3 lab/bot.py --runtime /path/to/bot-runtime --server cs.mahaloz.re:27015 --team t --visualize --seconds 60 --record bot.jsonl
```

Python chooses movement, searches the Dust2 waypoint graph with A*, selects
opponents, and aims/fires. The native engine provides network transport,
prediction, and animated pose data. Add `--headless` for Xvfb and software
OpenGL, or use the normal window. Ctrl-C cleans up the bot; external actions
expire after 250 ms without updates. The supplied graph is specific to Dust2,
and navigation is approximate. After 1.2 seconds without progress toward its next
waypoint, the bot tries a jump with a short randomized sidestep. Recovery retries
have a cooldown, prefer the clearer side, and appear as `unstick` in the live
map and decision log. Avoid running another telemetry receiver on the bot's
port while its controller is active.

The bot's default in-game name is `mahaloz-bot`; override it with `--name`.
`--visualize` prints a local browser URL (by default
`http://127.0.0.1:49302/`) with the bot's position and facing, planned A* route,
goal, recent movement, observed players, and selected target. It uses the Dust2
overview from the bot runtime when available, otherwise the waypoint graph.
Cached player observations appear as fading hollow markers. The sidebar shows
the current decision, health, and clip count. The viewer works with `--headless`
and shares the controller's observations without taking another telemetry port.
Use `--visualize-port` to choose a different HTTP port. For a remote controller,
forward that port with SSH, for example `ssh -L 49302:127.0.0.1:49302 HOST`,
then open the URL locally. The viewer listens only on loopback and closes when
the controller exits. Decision recordings also include the name, route, and goal.

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

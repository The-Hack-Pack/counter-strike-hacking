# Rehearsal evidence

These are measurements from actual Linux clients connected to dedicated Xash
servers, not simulated game results. The final client was also checked through
the public endpoint `cs.mahaloz.re:27015`. Raw JSON and console output accompany
the screenshots so the server's state can be distinguished from the client's
display.

| Demonstration | Observed result | Evidence |
|---|---|---|
| Find the magazine | Integer search narrowed 3,339 → 22 → 11 → 5 while firing 30 → 29 → 28 → 27 | [search](ammo-memory-search.json) |
| Edit local memory | Confirmed HUD address changed 27 → 99; server still had 27 | [local write](ammo-local-write.json) |
| Persistent binary patch | HUD stayed 99; server clip reached 0; target health stayed 9825 under extra attack inputs | [binary test](ammo-binary-patch.json), [screenshot](ammo-binary-patch.png) |
| Patch the original client | Exactly six bytes changed in the original prepared library, with no source overlay; HUD 99 while server clip stayed 0 under continued attacks | [original test](original-binary-patch.json), [original screenshot](original-binary-patch.png) |
| Find the clock | 1.0 → 1.5 → 2.0 → 1.0 isolated a single `sys_timescale.value` address | [float search](speed-memory-search.json) |
| Accelerate accepted movement | Direct memory write to 3.0: 349.477 units versus 124.062 at 1.0 for approximately half a second of forward input, after coasting stopped | [measurement](speed-accepted.json) |
| Restore temporal defense | Server emitted three “time is faster than server time” warnings with validation enabled and kicks disabled | [server log](speed-protected.log) |
| Automate jumps | One height peak without automation; four with it over 2.8 seconds | [jump samples](bunny-hop.json) |
| See through solid geometry | Opponent position was fresh while the world trace was blocked; box rendered through a solid crate with stock PVS enabled | [state](wallhack-stock-pvs.json), [screenshot](wallhack-stock-pvs.png) |
| Show all-map replication | Stock PVS left the distant opponent stale; deliberate server oversharing made its current position fresh | [comparison](full-map-visibility.json), [radar](full-map-radar.png) |
| Aim at heads | Final public-server test showed `headshot_death: 1`; earlier ordinary death message also confirmed a headshot | [final test](final-public-headshot.json), [earlier server test](aim-server-headshot.json) |
| Independent Python bot | Own player slot; search → pursue → engage; public server recorded an AK-47 kill, and native death message confirmed a headshot | [final bot test](final-public-python-bot.json), [earlier search test](python-bot.json) |

The bot's [complete decision log](final-public-python-bot.jsonl) contains its own
client observations and actual action tuples; its [native engine log](final-public-python-bot.engine.log)
contains the ordinary death message.
It uses the native engine for the complete network connection and Python for
decisions; it does not obtain enemy positions from the server console. Head
targeting remains subject to spread, latency, and pose differences, so every
bullet is not guaranteed to be a headshot. A nearby stationary test target
makes the aiming result easier to reproduce.

The original runtime's library is pinned by SHA-256
`559503cc93db2b604ffa395c754ca24951e086a65a1563af1b0ed77e7a6ed67d`.
The final overlay is
`5b8640c381ef13497dfba5e28c901a3e1f877f06110de278aabe8958f905b814`.
Earlier measurement records retain their original build/context information.
Final changes improved startup connection identifiers and automatic buying;
the final public-server aiming and bot checks use the final overlay.

[Deployment metadata](server-deployment.json) records the old server backup and
the deployed image. Docker export/import changed the image config IDs, while
the filesystem layers and the actual running engine/game-library hashes match
the tested server. The existing public forwarding to `192.168.0.25:27015` was
preserved. A temporary port used while preparing the deployment was removed.

[Final readiness](final-readiness.json) records the healthy public server after
restart, every requested startup setting, and the unpatched prepared client
libraries. [Package validation](package-validation.json) records installation,
binary patch/undo, removal, exact original-library restoration, and recovery of
the student's previous function keys while retaining other changed settings.

[Tool checks](tool-tests.log) verify that the patch changes exactly the intended
six bytes and restores the exact original file, rejects an unknown build,
refuses undo after unrelated changes, writes only the selected typed memory
address, and refuses writes into a read-only mapping. A running mapped library
must be closed before binary patching or uninstalling.

Use [the client lab instructions](../README.md) for installation, feature controls,
tools, and rollback. Memory addresses and player slots vary between
runs; the evidence is not a list of fixed addresses to paste into another game.

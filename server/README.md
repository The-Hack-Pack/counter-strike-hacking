# Counter-Strike dedicated server

This is a Linux amd64 Xash3D FWGS dedicated server for the
[CS16Client](https://github.com/Velaron/cs16-client) in `~/github/cs16-client`.
The image builds pinned engine and ReGameDLL sources; the game library revision
matches that client's `3rdparty/ReGameDLL_CS` submodule at client commit
`6a49bcc6f5292dec13046b23140c1e555dca8b31`. This is a protocol-49 Xash server;
use CS16Client with Xash3D FWGS to connect, rather than the stock Steam client.

The class deployment was shut down on 2026-10-17 with `docker compose down`.
Its container was removed, so it will not restart on host reboot. Downloaded
assets and generated navigation data remain in the Docker volume for reuse.
The instructions below are for explicitly starting a future deployment.

## Run

```sh
cd server
docker compose up -d --build
docker compose logs -f
```

The first startup downloads Valve's HLDS Counter-Strike assets anonymously using
SteamCMD (app 90). Allow several minutes and sufficient disk space for the assets
and build cache. SteamCMD sometimes needs multiple attempts; startup retries up
to five times and checks required files. Assets stay in the `game-data` Docker
volume across rebuilds and restarts. No Steam credentials are needed. Clients
still need their own game assets as described in CS16Client's instructions.

The server runs as an unprivileged user, publishes UDP 27015, starts `de_dust2`
with 32 slots, and restarts unless explicitly stopped. Public master-server
listing is disabled; players connect directly. Remote console and cheats are
disabled by default. Logs are rotated by Docker.

Built-in ReGameDLL bots keep ten active participants using `bot_quota_mode fill`:
an empty server has five bots per team; one playing human leaves nine bots;
ten or more playing humans leave no bots. The server accepts up to 32
players, with automatic team balancing and `mp_limitteams 1` for 16 versus 16.
This engine's protocol encodes player slots with five bits, so 32 is the hard
limit; setting `MAXPLAYERS=40` is clamped to 32. Raising that limit requires
coordinated engine/protocol and game-code changes on both servers and clients.
Spectators occupy slots but do not count toward the ten active participants.
Bot counts adjust at round boundaries; bots also vacate slots for joining humans.
The optional `classroom.cfg` deliberately disables team balancing for practice.

`game_init.cfg` enables bots before the game initializes, and `BotProfile.db`
provides the server's bot names and skill settings. Voice chatter is disabled.
On a map's first use, bots generate navigation data, briefly pausing normal play;
the generated `.nav` files persist in the game-data volume for future starts.

The Hack Pack lecture image applies the two small source patches in this
directory. Startup now sets `sv_speedhack_kick 0`, `hp_validate_cmdtime 0`, and
`sv_enablebunnyhopping 1`; ammo stays authoritative with `mp_infinite_ammo 0`.
The timing switch defaults to 1 in the engine itself, so the upstream check
remains active unless explicitly disabled by configuration.

Use `exec classroom.cfg` in the server console for the instructor's practice
rules and repeatable positioning/equipment controls. `exec protected.cfg`
restores timing/bunny-hop protections and disables fixture/oversharing controls.
`exec server.cfg` restores the requested permissive startup profile and the
ordinary round/buying rules. Client installation and controls are documented in
[lab/README.md](../lab/README.md).

The class deployment ran on `192.168.0.25` at `cs.mahaloz.re:27015` until its
shutdown. The lecture image and configs were deployed there through
the existing `honohono-local` SSH profile; the instructor's Linux workstation is
`192.168.0.52`, which also has a local test server. From the instructor checkout,
`../lab/server.sh 'hp_dump'` (or `./lab/server.sh` from the repository root)
controls the public host. It uses a task-local known-hosts file whose keys were
matched against the user's existing trusted keys, without changing global SSH
configuration. The pre-lecture image is retained as
`counter-strike-server:pre-hackpack-20261012`, and the old server directory is
backed up on the public host at
`/home/mahaloz/.cache/hackpack-lecture-20261012/server-before.tar.gz`.

```sh
docker compose ps
docker compose restart server
docker compose down             # retains downloaded assets
```

Edit `server.cfg` or `mapcycle.txt`, then restart the service. Optional `.env`
settings (run `docker compose up -d` after editing these):

```dotenv
MAP=de_dust2
MAXPLAYERS=32
PORT=27015
BIND_IP=0.0.0.0
```

To refresh game assets, remove the install marker and restart:

```sh
docker compose exec server rm /data/.assets-installed
docker compose restart server
```

If SteamCMD cannot download the assets, inspect `docker compose logs` for the
Valve error. Do not treat a running container as a working server: wait for its
health check to pass. `docker compose down -v` deletes all downloaded game data.

## DNS and router

Cloudflare's ordinary orange-cloud proxy does **not** forward Counter-Strike's
UDP traffic. For `cs.mahaloz.re`:

1. Set its Cloudflare A record to the router's public IPv4 address and select
   **DNS only** (gray cloud). Remove any AAAA record unless you also configure a
   working IPv6 route; this Compose setup publishes IPv4.
2. Forward **UDP 27015** on the router to **192.168.0.25:27015**, and allow it
   through any host/upstream firewall. Reserve that LAN address for this host.
3. Test from outside the LAN. Testing the public name inside the LAN depends on
   the router supporting NAT loopback. Behind CGNAT, obtain a public address or
   use an appropriate UDP relay.

If you already have Cloudflare Spectrum supporting arbitrary UDP applications,
configure UDP 27015 to the origin instead, with Proxy Protocol disabled (Xash
does not understand Cloudflare's Simple Proxy Protocol header). Ordinary
Cloudflare proxying and HTTP tunnels are not substitutes for that configuration.
See [Cloudflare network ports](https://developers.cloudflare.com/fundamentals/reference/network-ports/)
and [Spectrum](https://developers.cloudflare.com/spectrum/).

On this host, the initial deployment changed `cs.mahaloz.re` to DNS-only and
created a UPnP mapping on `192.168.0.1` from public UDP 27015 to
`192.168.0.25:27015`, with no lease expiry. That mapping was removed when the
class server was shut down on 2026-10-17. A router reboot can also erase UPnP
mappings. For persistence across router reboots, add the equivalent permanent
forward in the router UI. To recreate the UPnP mapping from this host:

```sh
docker run --rm --network host alpine:3.22 sh -c \
  'apk add --no-cache miniupnpc && upnpc -e "Counter-Strike cs.mahaloz.re" -a 192.168.0.25 27015 27015 UDP 0'
```

If the ISP changes the public IPv4 address, update the DNS record accordingly.

## Connect and verify

In the Xash3D/CS16Client console:

```text
connect cs.mahaloz.re:27015
```

On the same LAN, use `connect 192.168.0.25:27015` if the router lacks NAT loopback.

The Python probe uses only the standard library and verifies server discovery,
Counter-Strike game identity, a challenge response, and acceptance of a
protocol-49 connection. From the repository root:

```sh
python3 server/probe.py 127.0.0.1
python3 server/probe.py 192.168.0.25
python3 server/probe.py cs.mahaloz.re  # also run on a machine outside this LAN
```

Success prints `"connection": "accepted (protocol 49)"`. This verifies connection
admission, not rendered gameplay or a complete map download. Each full probe
briefly occupies a player slot, which expires after 60 seconds. The container's
health check uses `--query-only`, which does not occupy slots. A healthy local
container does not prove that router forwarding or public DNS is correct.

Source revisions are build arguments in `Dockerfile`. When upgrading the client,
check its ReGameDLL submodule and rebuild with a compatible engine revision.

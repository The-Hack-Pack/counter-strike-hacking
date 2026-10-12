# Counter-Strike dedicated server

This is a Linux amd64 Xash3D FWGS dedicated server for the
[CS16Client](https://github.com/Velaron/cs16-client) in `~/github/cs16-client`.
The image builds pinned engine and ReGameDLL sources; the game library revision
matches that client's `3rdparty/ReGameDLL_CS` submodule at client commit
`6a49bcc6f5292dec13046b23140c1e555dca8b31`. This is a protocol-49 Xash server;
use CS16Client with Xash3D FWGS to connect, rather than the stock Steam client.

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
with 16 slots, and restarts unless explicitly stopped. Public master-server
listing is disabled; players connect directly. Remote console and cheats are
disabled by default. Logs are rotated by Docker.

```sh
docker compose ps
docker compose restart server
docker compose down             # retains downloaded assets
```

Edit `server.cfg` or `mapcycle.txt`, then restart the service. Optional `.env`
settings (run `docker compose up -d` after editing these):

```dotenv
MAP=de_dust2
MAXPLAYERS=16
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
`192.168.0.25:27015`, with no lease expiry. A router reboot can still erase UPnP
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

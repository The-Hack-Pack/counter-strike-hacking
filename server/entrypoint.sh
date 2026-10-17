#!/bin/sh
set -eu

# HLDS (app 90) provides the official server assets anonymously. SteamCMD can
# require repeated installs before its Counter-Strike depot is complete.
if [ ! -f /data/.assets-installed ]; then
    for attempt in 1 2 3 4 5; do
        echo "Installing Valve Counter-Strike assets (attempt $attempt/5)..."
        if /opt/steamcmd/steamcmd.sh +force_install_dir /data +login anonymous \
            +app_set_config 90 mod cstrike +app_update 90 validate +quit \
            && [ -f /data/cstrike/maps/de_dust2.bsp ] \
            && [ -f /data/cstrike/models/player/leet/leet.mdl ] \
            && [ -f /data/valve/halflife.wad ]; then
            touch /data/.assets-installed
            break
        fi
    done
    if [ ! -f /data/.assets-installed ]; then
        echo "SteamCMD did not install complete assets. See server/README.md." >&2
        exit 1
    fi
fi

cp -a /opt/xash/. /data/
cp /config/server.cfg /data/cstrike/server.cfg
cp /config/game_init.cfg /data/cstrike/game_init.cfg
cp /config/BotProfile.db /data/cstrike/BotProfile.db
cp /config/classroom.cfg /data/cstrike/classroom.cfg
cp /config/protected.cfg /data/cstrike/protected.cfg
cp /config/mapcycle.txt /data/cstrike/mapcycle.txt
exec /data/xash -dedicated -console -game cstrike -ip 0.0.0.0 -port 27015 \
    -nomaster +maxplayers "${MAXPLAYERS:-32}" +map "${MAP:-de_dust2}"

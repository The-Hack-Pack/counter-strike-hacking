FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake git python3 pkg-config zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
ARG XASH_REV=fd0cd6afdda9dff94346af60884b99876001ca5f
# Matches cs16-client 6a49bcc6f5292dec13046b23140c1e555dca8b31's submodule.
ARG REGAMEDLL_REV=7be9d59dca1ee11d270e4631d7e3be0c67a1a82b
RUN git init /src/xash && cd /src/xash \
    && git remote add origin https://github.com/FWGS/xash3d-fwgs.git \
    && git fetch --depth 1 origin "$XASH_REV" && git checkout FETCH_HEAD \
    && git submodule update --init --depth 1 3rdparty/library_suffix 3rdparty/libbacktrace/libbacktrace \
    && ./waf configure --dedicated --64bits --disable-mbedtls --prefix=/ \
    && ./waf build -j4 && ./waf install --destdir=/opt/xash
RUN git init /src/regame && cd /src/regame \
    && git remote add origin https://github.com/Velaron/ReGameDLL_CS.git \
    && git fetch --depth 1 origin "$REGAMEDLL_REV" && git checkout FETCH_HEAD \
    && cmake -S . -B build -DXASH_COMPAT=ON -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/xash \
    && cmake --build build -j4 && cmake --install build

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl lib32gcc-s1 lib32stdc++6 libstdc++6 python3 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 cs \
    && mkdir -p /opt/steamcmd /data && chown cs:cs /opt/steamcmd /data
USER cs
RUN curl -fsSL --retry 3 https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz \
    | tar -xz -C /opt/steamcmd
COPY --from=build /opt/xash /opt/xash
COPY --chmod=755 entrypoint.sh /usr/local/bin/cs-server
COPY probe.py /opt/probe.py
WORKDIR /data
EXPOSE 27015/udp
ENTRYPOINT ["cs-server"]

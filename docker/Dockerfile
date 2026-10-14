# Userspace WireGuard as fallback for hosts without the kernel module (OpenVZ/LXC VPS etc.).
FROM golang:1.24-bookworm AS wireguard-go
RUN CGO_ENABLED=0 GOBIN=/out go install golang.zx2c4.com/wireguard@v0.0.0-20250521234502-f333402bd9cb \
 && mv /out/wireguard /out/wireguard-go

FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends wireguard-tools iptables iproute2 qrencode python3 procps \
 && rm -rf /var/lib/apt/lists/*
COPY --from=wireguard-go /out/wireguard-go /usr/local/bin/wireguard-go
COPY neuvpn /opt/neuvpn/neuvpn
COPY docker/entrypoint.sh /entrypoint.sh
RUN printf '#!/bin/sh\nPYTHONPATH=/opt/neuvpn exec python3 -m neuvpn "$@"\n' > /usr/local/bin/neuvpn \
 && chmod 755 /usr/local/bin/neuvpn /entrypoint.sh
ENV NEUVPN_DIR=/etc/neuvpn
VOLUME /etc/neuvpn
EXPOSE 51820/udp
ENTRYPOINT ["/entrypoint.sh"]

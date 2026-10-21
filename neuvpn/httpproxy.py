"""Small HTTP proxy in front of Tor's SOCKS port.

Phones (iPhone/Android Wi-Fi settings) only support HTTP proxies. Tor's own
HTTPTunnelPort understands CONNECT only, so plain http:// pages would fail.
This proxy handles both: CONNECT (https) and absolute-URI requests (http), and
sends everything through Tor's SOCKS port.

Run: python -m neuvpn.httpproxy LISTEN_HOST LISTEN_PORT SOCKS_PORT [--lan-only]
"""

import ipaddress
import socket
import socketserver
import sys
import threading
import urllib.parse

from .geo import socks5_connect

_BUF = 65536


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(_BUF):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _read_head(sock: socket.socket) -> tuple[bytes, bytes]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(_BUF)
        if not chunk:
            raise ConnectionError("Verbindung vor Ende des Headers geschlossen")
        data += chunk
        if len(data) > 64 * 1024:
            raise ConnectionError("Header zu groß")
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def rewrite_request(head: bytes) -> tuple[str, int, bytes]:
    """Turn a proxy request ('GET http://host/path HTTP/1.1') into an origin request.

    Returns (host, port, new_head). Keep-alive is switched off so that each
    client connection carries exactly one request to one host.
    """
    lines = head.decode("iso-8859-1").split("\r\n")
    method, target, version = lines[0].split(" ", 2)
    url = urllib.parse.urlsplit(target)
    if url.scheme != "http" or not url.hostname:
        raise ValueError(f"Nicht unterstützt: {target}")
    path = (url.path or "/") + (f"?{url.query}" if url.query else "")
    headers = [
        line for line in lines[1:]
        if line.split(":", 1)[0].strip().lower()
        not in ("proxy-connection", "connection", "keep-alive", "proxy-authorization")
    ]
    if not any(h.lower().startswith("host:") for h in headers):
        headers.insert(0, f"Host: {url.netloc}")
    new = "\r\n".join([f"{method} {path} {version}", *headers, "Connection: close"]) + "\r\n\r\n"
    return url.hostname, url.port or 80, new.encode("iso-8859-1")


class _Handler(socketserver.BaseRequestHandler):
    server: "ProxyServer"

    def handle(self) -> None:
        client = self.request
        client.settimeout(120)
        try:
            head, rest = _read_head(client)
            first = head.split(b"\r\n", 1)[0].decode("iso-8859-1")
            method, target, _ = first.split(" ", 2)
            if method.upper() == "CONNECT":
                host, _, port = target.rpartition(":")
                upstream = socks5_connect(self.server.socks, host.strip("[]"), int(port), 60)
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                if rest:
                    upstream.sendall(rest)
            else:
                host, port, new_head = rewrite_request(head)
                upstream = socks5_connect(self.server.socks, host, port, 60)
                upstream.sendall(new_head + rest)
        except (OSError, ValueError) as exc:
            try:
                msg = f"neuvpn-Proxy: {exc}".encode("utf-8", "replace")
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n"
                               b"Content-Type: text/plain; charset=utf-8\r\n"
                               b"Content-Length: " + str(len(msg)).encode() + b"\r\n\r\n" + msg)
            except OSError:
                pass
            return
        upstream.settimeout(None)
        client.settimeout(None)
        t = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
        t.start()
        _pipe(client, upstream)
        t.join()
        upstream.close()


class ProxyServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, listen: tuple[str, int], socks: tuple[str, int], lan_only: bool):
        self.socks = socks
        self.lan_only = lan_only
        super().__init__(listen, _Handler)

    def verify_request(self, request, client_address) -> bool:
        if not self.lan_only:
            return True
        try:
            addr = ipaddress.ip_address(client_address[0])
        except ValueError:
            return False
        return addr.is_private or addr.is_loopback


def main(argv: list[str]) -> None:
    host, port, socks_port = argv[0], int(argv[1]), int(argv[2])
    server = ProxyServer((host, port), ("127.0.0.1", socks_port), "--lan-only" in argv)
    if "--watch" in argv:  # --watch COUNTRY TOR_DIR CONTROL_PORT
        from pathlib import Path

        from . import tor

        i = argv.index("--watch")
        country, base, control = argv[i + 1], Path(argv[i + 2]), int(argv[i + 3])
        threading.Thread(target=tor.watch_exit_country, daemon=True,
                         args=(tor.TorPaths(base), country, socks_port, control)).start()
    server.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])

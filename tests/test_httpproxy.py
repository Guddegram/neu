import http.server
import socket
import threading
import unittest

from neuvpn import httpproxy
from tests.test_tor import _fake_socks_server


class _Echo(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"path={self.path} host={self.headers['Host']} conn={self.headers['Connection']}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _request(proxy_port: int, raw: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=10) as s:
        s.sendall(raw)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return data


class HttpProxyTest(unittest.TestCase):
    def setUp(self):
        self.web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
        threading.Thread(target=self.web.serve_forever, daemon=True).start()
        self.addCleanup(self.web.shutdown)
        self.connections = []
        self.socks = _fake_socks_server(self.connections)
        self.addCleanup(self.socks.close)
        self.proxy = httpproxy.ProxyServer(("127.0.0.1", 0), self.socks.getsockname(), lan_only=True)
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()
        self.addCleanup(self.proxy.shutdown)
        self.port = self.proxy.server_address[1]

    def test_plain_http_goes_through_socks(self):
        web_port = self.web.server_port
        raw = (f"GET http://site.example:{web_port}/a?b=1 HTTP/1.1\r\nHost: site.example:{web_port}\r\n"
               "Proxy-Connection: keep-alive\r\n\r\n").encode()
        reply = _request(self.port, raw)
        self.assertIn(b"200 OK", reply)
        self.assertIn(f"path=/a?b=1 host=site.example:{web_port} conn=close".encode(), reply)
        self.assertEqual(self.connections, [("site.example", web_port)])  # DNS via the proxy

    def test_connect_tunnel(self):
        web_port = self.web.server_port
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(f"CONNECT tunnel.example:{web_port} HTTP/1.1\r\n\r\n".encode())
            self.assertIn(b"200 Connection established", s.recv(1024))
            s.sendall(b"GET /x HTTP/1.0\r\nHost: tunnel.example\r\n\r\n")
            data = b""
            while chunk := s.recv(65536):
                data += chunk
        self.assertIn(b"path=/x", data)
        self.assertEqual(self.connections, [("tunnel.example", web_port)])

    def test_bad_request_gets_502(self):
        reply = _request(self.port, b"GET ftp://x/ HTTP/1.1\r\n\r\n")
        self.assertIn(b"502 Bad Gateway", reply)

    def test_lan_only(self):
        self.assertTrue(self.proxy.verify_request(None, ("192.168.1.20", 5000)))
        self.assertTrue(self.proxy.verify_request(None, ("127.0.0.1", 5000)))
        self.assertFalse(self.proxy.verify_request(None, ("8.8.8.8", 5000)))

    def test_rewrite_request(self):
        host, port, head = httpproxy.rewrite_request(
            b"GET http://a.example/p HTTP/1.1\r\nProxy-Connection: keep-alive\r\nAccept: */*")
        self.assertEqual((host, port), ("a.example", 80))
        self.assertEqual(head, b"GET /p HTTP/1.1\r\nHost: a.example\r\nAccept: */*\r\n"
                               b"Connection: close\r\n\r\n")


if __name__ == "__main__":
    unittest.main()

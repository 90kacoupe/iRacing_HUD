"""Small local web server. Overlays add routes (e.g. the dash's /data) and folders to serve.

It also lets a second launch of the app ask the running copy to open its settings (/show).
"""
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


def json_response(obj, code=200):
    body = obj if isinstance(obj, bytes) else json.dumps(obj, indent=1).encode()
    return code, {"Content-Type": "application/json"}, body


def redirect(location):
    return 302, {"Location": location}, b""


class HudServer:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.routes = {}   # exact path -> fn(query) -> (code, headers, body)
        self.mounts = []   # (url prefix, folder)
        self.error = None
        self._httpd = None

    def route(self, path, fn):
        self.routes[path] = fn

    def mount(self, prefix, folder):
        self.mounts.append((prefix, os.path.abspath(folder)))

    def url(self, path=""):
        return f"http://127.0.0.1:{self.port}{path}"

    def start(self):
        server = self

        class Handler(SimpleHTTPRequestHandler):
            # Keep-alive: a dash page polls /data ~30 times a second. With HTTP/1.0 each poll
            # was a new connection and a new server thread; now one connection (and one
            # thread) serves them all. Every reply sends Content-Length, which this needs.
            protocol_version = "HTTP/1.1"
            timeout = 15          # close a connection nobody has used for 15 s

            def do_GET(self):
                parts = urlsplit(self.path)
                fn = server.routes.get(parts.path)
                if fn:
                    try:
                        code, headers, body = fn(parts.query)
                    except Exception as e:
                        code, headers, body = json_response({"error": repr(e)}, 500)
                    self.send_response(code)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

            def translate_path(self, path):
                p = unquote(urlsplit(path).path)
                for prefix, folder in server.mounts:
                    if p.startswith(prefix):
                        full = os.path.normpath(os.path.join(folder, p[len(prefix):].lstrip("/\\")))
                        if full == folder or full.startswith(folder + os.sep):
                            return full
                return os.path.join(os.path.dirname(__file__), "__nothing_here__")

            def log_message(self, *args):
                pass

        ThreadingHTTPServer.allow_reuse_address = False   # never share the port with another copy
        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), partial(Handler))
        except OSError as e:
            self.error = (f"Port {self.port} is already in use (maybe the old dash overlay is still running). "
                          f"The dash can't load until it's free.")
            print(self.error, e)
            return False
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, daemon=True, name="server").start()
        return True

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()

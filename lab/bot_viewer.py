"""Read-only browser map fed by the Python controller's own observations."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
import time


def load_overview(runtime):
    """Use the runtime's overview without packaging or copying game assets."""
    if runtime is None:
        return None, None
    directory = Path(runtime) / 'cstrike' / 'overviews'
    try:
        text = (directory / 'de_dust2.txt').read_text()
        text = re.sub(r'//[^\n]*', '', text)
        number = r'(-?\d+(?:\.\d+)?)'
        zoom = float(re.search(r'\bZOOM\s+' + number, text, re.I)[1])
        origin = re.search(r'\bORIGIN\s+' + number + r'\s+' + number, text, re.I)
        rotated = bool(int(re.search(r'\bROTATED\s+(\d+)', text, re.I)[1]))
        bitmap = (directory / 'de_dust2.bmp').read_bytes()
        if zoom <= 0 or bitmap[:2] != b'BM':
            return None, None
        return {'zoom': zoom, 'origin': [float(origin[1]), float(origin[2])], 'rotated': rotated}, bitmap
    except (OSError, ValueError, TypeError):
        return None, None


class BotViewer:
    def __init__(self, nodes, name, port, runtime=None):
        self._lock = threading.Lock()
        self._snapshot = None
        self._updated = None
        self._name = name
        overview, bitmap = load_overview(runtime)
        graph = json.dumps({'nodes': nodes, 'overview': overview}, separators=(',', ':')).encode()
        page = Path(__file__).with_name('bot_viewer.html').read_bytes()
        viewer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split('?', 1)[0]
                if path == '/':
                    body, content_type = page, 'text/html; charset=utf-8'
                elif path == '/graph':
                    body, content_type = graph, 'application/json'
                elif path == '/state':
                    body, content_type = json.dumps(viewer.state()).encode(), 'application/json'
                elif path == '/overview.bmp' and bitmap is not None:
                    body, content_type = bitmap, 'image/bmp'
                elif path == '/favicon.ico':
                    self.send_response(204)
                    self.end_headers()
                    return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.url = f'http://127.0.0.1:{self._server.server_port}/'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def update(self, snapshot):
        with self._lock:
            self._snapshot = snapshot
            self._updated = time.monotonic()

    def state(self):
        with self._lock:
            return {'name': self._name, 'snapshot': self._snapshot,
                    'age': None if self._updated is None else time.monotonic() - self._updated}

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

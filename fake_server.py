import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Фейковый сервер, чтобы Render думал, что мы слушаем порт
def run_fake_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    port = int(os.environ.get("PORT", 10000))  # Render требует переменную PORT
    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


import http.server
import socketserver
import os

PORT = 8000
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # корінь — поточна папка

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # тихіший лог

with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
    print(f"Serving on http://127.0.0.1:{PORT}/app/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")

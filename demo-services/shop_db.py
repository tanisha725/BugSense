"""shop-db: a pretend database for the demo shop.

It answers two web requests on port 9102:
  /health  - "I am alive"
  /query   - pretends to run a database query

Stopping this program is how the demo shows "the database went down".
"""

import json
import random
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = "shop-db"
PORT = 9102


def log(level, message):
    """Prints one log line in the format BugSense understands."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} {level} [{SERVICE}] {message}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        request_id = self.headers.get("X-Request-ID", "-")
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        elif self.path == "/query":
            time.sleep(random.uniform(0.005, 0.03))  # a real query takes a little time
            log("INFO", f"Query served: SELECT order request_id={request_id}")
            self.reply(200, {"rows": 1})
        else:
            self.reply(404, {"error": "not found"})

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *args):
        pass  # the built-in access log is replaced by our own log lines


if __name__ == "__main__":
    log("INFO", f"Database listening on port {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

"""shop-api: the checkout API of the demo shop.

It answers on port 9101:
  /health    - healthy only if it can reach shop-db
  /checkout  - places an order by asking shop-db

The environment variable SHOP_FAULT switches on a failure for the demo:
  crash       - starts, then crashes with an unhandled error (crash loop)
  bad-config  - starts with a broken database address and refuses to run
  slow        - many requests become slow, some time out
"""

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = "shop-api"
PORT = 9101
FAULT = os.environ.get("SHOP_FAULT", "")
DB_URL = "postgres//127.0.0.1:9102" if FAULT == "bad-config" else "http://127.0.0.1:9102"

# Talk to the other services directly. (By default Python first looks up the
# computer's proxy settings, which can make the first request hang on a Mac.)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(level, message):
    """Prints one log line in the format BugSense understands."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} {level} [{SERVICE}] {message}", flush=True)


def ask_database(path, request_id):
    request = urllib.request.Request(f"{DB_URL}{path}", headers={"X-Request-ID": request_id})
    with OPENER.open(request, timeout=1) as response:
        return json.loads(response.read())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        request_id = self.headers.get("X-Request-ID", "req-none")
        if self.path == "/health":
            try:
                ask_database("/health", request_id)
                self.reply(200, {"status": "ok", "database": "ok"})
            except OSError:
                self.reply(503, {"status": "unhealthy", "database": "unreachable"})
        elif self.path == "/checkout":
            self.checkout(request_id)
        else:
            self.reply(404, {"error": "not found"})

    def checkout(self, request_id):
        started = time.time()
        if FAULT == "slow" and random.random() < 0.6:
            time.sleep(random.uniform(1.5, 3.0))  # something makes requests hang
        try:
            ask_database("/query", request_id)
        except OSError as problem:
            reason = getattr(problem, "reason", problem)
            log("ERROR", f"OperationalError: connection to shop-db at 127.0.0.1:9102 failed: {reason} request_id={request_id}")
            log("ERROR", f"GET /checkout returned 503 Service Unavailable request_id={request_id}")
            self.reply(503, {"error": "database unavailable"})
            return
        took = (time.time() - started) * 1000
        level = "WARNING" if took > 1000 else "INFO"
        log(level, f"GET /checkout 200 in {took:.0f} ms request_id={request_id}")
        self.reply(200, {"order": "created"})

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *args):
        pass


def check_config():
    """A real service checks its settings before it starts."""
    if not DB_URL.startswith("http://"):
        log("ERROR", f'ConfigError: invalid SHOP_DB_URL: expected "http://", got "{DB_URL}"')
        log("CRITICAL", "Startup failed: invalid configuration")
        sys.exit(1)


if __name__ == "__main__":
    log("INFO", f"Starting shop-api on port {PORT}")
    check_config()
    if FAULT == "crash":
        time.sleep(1.5)
        log("CRITICAL", "Unhandled exception, shutting down")
        # No try/except on purpose: Python prints a real traceback and the program exits
        raise RuntimeError("payment module failed to initialise: missing key 'currency'")
    log("INFO", "Ready to take orders")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

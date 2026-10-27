"""shop-web: the web front end of the demo shop.

It has no port. Instead it behaves like customers: once a second it opens the
checkout page, which calls shop-api. Each visit gets a request ID, so one
failed visit can be followed through all three services.
"""

import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

SERVICE = "shop-web"
API_URL = "http://127.0.0.1:9101/checkout"

# Talk to shop-api directly. (By default Python first looks up the computer's
# proxy settings, which can make the first request hang on a Mac.)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(level, message):
    """Prints one log line in the format BugSense understands."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} {level} [{SERVICE}] {message}", flush=True)


def visit_checkout():
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    started = time.time()
    request = urllib.request.Request(API_URL, headers={"X-Request-ID": request_id})
    try:
        with OPENER.open(request, timeout=2):
            pass
        log("INFO", f"Checkout page loaded in {(time.time() - started) * 1000:.0f} ms request_id={request_id}")
    except urllib.error.HTTPError as problem:
        log("ERROR", f"Checkout page failed: upstream returned {problem.code} request_id={request_id}")
    except TimeoutError:
        log("ERROR", f"TimeoutError: shop-api did not answer within 2000 ms request_id={request_id}")
    except urllib.error.URLError as problem:
        if isinstance(problem.reason, TimeoutError):
            log("ERROR", f"TimeoutError: shop-api did not answer within 2000 ms request_id={request_id}")
        else:
            log("ERROR", f"ConnectionError: shop-api unreachable ({problem.reason}) request_id={request_id}")


if __name__ == "__main__":
    log("INFO", "Web front end started, sending a checkout every second")
    while True:
        visit_checkout()
        time.sleep(1)

"""shop-web: the web front end of the demo shop.

It has no port. Instead it behaves like customers: once a second it opens the
checkout page, which calls shop-api. Each visit gets a request ID, so one
failed visit can be followed through all three services. Each visit also
starts an OpenTelemetry trace that shop-api and shop-db continue (see otel.py).
"""

import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

import otel

SERVICE = "shop-web"
API_URL = "http://127.0.0.1:9101/checkout"

# Talk to shop-api directly. (By default Python first looks up the computer's
# proxy settings, which can make the first request hang on a Mac.)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
telemetry = otel.setup(SERVICE)


def log(level, message):
    """Prints one log line in the format BugSense understands."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trace_id = telemetry.trace_id()
    suffix = f" trace_id={trace_id}" if trace_id else ""
    print(f"{now} {level} [{SERVICE}] {message}{suffix}", flush=True)


def visit_checkout():
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    started = time.time()
    attributes = {"http.request.method": "GET", "url.full": API_URL, "request_id": request_id}
    with telemetry.span("GET /checkout", kind="client", attributes=attributes) as span:
        status = call_api(request_id, started, span)
    telemetry.record(time.time() - started, {"http.route": "/checkout", "http.response.status_code": status})


def call_api(request_id, started, span):
    """One checkout visit. Returns the HTTP status (0 when there was no answer)."""
    headers = {"X-Request-ID": request_id}
    telemetry.inject(headers)  # the trace continues in shop-api
    request = urllib.request.Request(API_URL, headers=headers)
    try:
        with OPENER.open(request, timeout=2):
            pass
        log("INFO", f"Checkout page loaded in {(time.time() - started) * 1000:.0f} ms request_id={request_id}")
        return 200
    except urllib.error.HTTPError as problem:
        telemetry.fail(span, f"upstream returned {problem.code}")
        log("ERROR", f"Checkout page failed: upstream returned {problem.code} request_id={request_id}")
        return problem.code
    except TimeoutError:
        telemetry.fail(span, "shop-api did not answer within 2000 ms")
        log("ERROR", f"TimeoutError: shop-api did not answer within 2000 ms request_id={request_id}")
    except urllib.error.URLError as problem:
        if isinstance(problem.reason, TimeoutError):
            telemetry.fail(span, "shop-api did not answer within 2000 ms")
            log("ERROR", f"TimeoutError: shop-api did not answer within 2000 ms request_id={request_id}")
        else:
            telemetry.fail(span, f"shop-api unreachable ({problem.reason})")
            log("ERROR", f"ConnectionError: shop-api unreachable ({problem.reason}) request_id={request_id}")
    return 0


if __name__ == "__main__":
    log("INFO", "Web front end started, sending a checkout every second")
    while True:
        visit_checkout()
        time.sleep(1)

"""OpenTelemetry for the demo shop: traces and metrics, sent to BugSense.

Each service calls setup("shop-api") once. After that:

  with telemetry.span("GET /checkout", kind="server", headers=request_headers):
      ...                         # one step of a request (a span)
  telemetry.inject(headers)       # passes the trace on to the next service
  telemetry.record(seconds, ...)  # adds one request duration to the histogram
  telemetry.trace_id()            # the current trace ID, written into log lines

The trace context travels between services in the standard W3C "traceparent"
HTTP header, so one checkout becomes ONE trace across shop-web, shop-api and
shop-db.

Data is sent with OTLP over HTTP to OTEL_EXPORTER_OTLP_ENDPOINT (BugSense sets
it when it starts the service). The resource attribute service.namespace
tells BugSense which project the data belongs to.

If the OpenTelemetry packages are missing, or no endpoint is set, every
function here does nothing, so the shop still runs.
"""

import os
import resource
import signal
import sys
from contextlib import contextmanager

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
PROJECT = os.environ.get("BUGSENSE_PROJECT", "Demo shop (live services)")

try:
    from opentelemetry import metrics, propagate, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.metrics import Observation
    from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider, ObservableCounter
    from opentelemetry.sdk.metrics.export import AggregationTemporality, PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import SpanKind, Status, StatusCode

    INSTALLED = True
except ImportError:
    INSTALLED = False

# Request durations in seconds: from 5 ms to 10 s
DURATION_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 2.5, 5, 10]


class Telemetry:
    """Real telemetry, used when OpenTelemetry is installed and an endpoint is set."""

    def __init__(self, service):
        resource_info = Resource.create({"service.name": service, "service.namespace": PROJECT})

        tracer_provider = TracerProvider(resource=resource_info)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"), schedule_delay_millis=1000)
        )
        trace.set_tracer_provider(tracer_provider)
        self.tracer = trace.get_tracer(service)

        # DELTA: each export says how much was added since the last one
        delta = {Counter: AggregationTemporality.DELTA, Histogram: AggregationTemporality.DELTA,
                 ObservableCounter: AggregationTemporality.DELTA}
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{ENDPOINT}/v1/metrics", preferred_temporality=delta),
            export_interval_millis=5000,
        )
        meter_provider = MeterProvider(
            resource=resource_info,
            metric_readers=[reader],
            views=[View(instrument_type=Histogram, aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS))],
        )
        metrics.set_meter_provider(meter_provider)
        meter = metrics.get_meter(service)

        self.duration = meter.create_histogram(
            "http.server.request.duration" if service != "shop-web" else "http.client.request.duration",
            unit="s",
            description="How long requests take",
        )
        # The process measures itself: CPU seconds used, and peak memory
        meter.create_observable_counter(
            "process.cpu.time", callbacks=[self._cpu], unit="s", description="CPU time used by the process"
        )
        meter.create_observable_gauge(
            "process.memory.usage", callbacks=[self._memory], unit="By", description="Peak memory of the process"
        )

        # BugSense stops services with SIGTERM. Exiting normally lets the SDK
        # send what it still holds before the process ends.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    @staticmethod
    def _cpu(_options):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        yield Observation(usage.ru_utime + usage.ru_stime)

    @staticmethod
    def _memory(_options):
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes, Linux reports kilobytes
        yield Observation(peak if sys.platform == "darwin" else peak * 1024)

    @contextmanager
    def span(self, name, kind="internal", headers=None, attributes=None):
        """One step of a request. headers: the incoming request's headers, to join its trace."""
        # urllib sends "Traceparent", the standard name is "traceparent": compare in lower case
        carrier = {key.lower(): value for key, value in headers.items()} if headers is not None else None
        context = propagate.extract(carrier) if carrier is not None else None
        span_kind = {"server": SpanKind.SERVER, "client": SpanKind.CLIENT}.get(kind, SpanKind.INTERNAL)
        with self.tracer.start_as_current_span(
            name, context=context, kind=span_kind, attributes=attributes or {},
            record_exception=False, set_status_on_exception=False,
        ) as current:
            yield current

    @staticmethod
    def fail(current, message):
        """Marks a span as failed, with the reason."""
        current.set_status(Status(StatusCode.ERROR, message))

    @staticmethod
    def inject(headers):
        propagate.inject(headers)

    def record(self, seconds, attributes):
        self.duration.record(seconds, attributes)

    @staticmethod
    def trace_id():
        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None


class NoTelemetry:
    """Used when OpenTelemetry is not available: does nothing."""

    @contextmanager
    def span(self, name, kind="internal", headers=None, attributes=None):
        yield None

    def fail(self, current, message):
        pass

    def inject(self, headers):
        pass

    def record(self, seconds, attributes):
        pass

    def trace_id(self):
        return None


def setup(service):
    if INSTALLED and ENDPOINT:
        return Telemetry(service)
    return NoTelemetry()

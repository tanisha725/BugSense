import { Fragment, useEffect, useState } from 'react'
import LineChart from '../components/LineChart.jsx'
import TraceWaterfall from '../components/TraceWaterfall.jsx'
import { getMetricNames, getMetricSeries, getTelemetryServices, getTrace, getTraces } from '../services/api.js'

const WINDOWS = [5, 15, 60]
const AGGREGATIONS = ['avg', 'p50', 'p95', 'p99', 'min', 'max', 'sum', 'count', 'rate', 'last']

function percent(value) {
  return `${(value * 100).toFixed(value > 0 && value < 0.1 ? 1 : 0)}%`
}

function ms(value) {
  return value === null || value === undefined ? '-' : `${Math.round(value)} ms`
}

// How a metric's values are written, from its unit
function formatterFor(series) {
  if (!series) return (value) => value
  if (series.unit === 'ms') return (value) => `${value.toFixed(0)} ms`
  if (series.unit === 's') return (value) => `${(value * 1000).toFixed(0)} ms`
  if (series.unit === 'ratio') return percent
  if (series.unit === 'By') return (value) => `${(value / 1e6).toFixed(1)} MB`
  return (value) => (Number.isInteger(value) ? value.toLocaleString() : value.toFixed(3))
}

// What OpenTelemetry tells us about each service: requests, errors, latency,
// CPU and memory, a chart of any metric, and every request as a trace.
function Telemetry({ project, projectId }) {
  const [windowMinutes, setWindowMinutes] = useState(15)
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)

  const [metricNames, setMetricNames] = useState([])
  const [chart, setChart] = useState({ service: '', metric: 'latency', aggregation: 'p95', step_seconds: 30 })
  const [series, setSeries] = useState(null)

  const [traceFilters, setTraceFilters] = useState({ status: 'ANY', service: '', min_duration_ms: '' })
  const [traces, setTraces] = useState([])
  const [openTrace, setOpenTrace] = useState(null)

  // Everything refreshes every 5 seconds: telemetry is live data
  useEffect(() => {
    let cancelled = false
    function load() {
      const scope = { project_id: projectId, window_minutes: windowMinutes }
      Promise.all([
        getTelemetryServices(scope),
        getMetricNames({ project_id: projectId }),
        getMetricSeries({ ...scope, ...chart }),
        getTraces({ ...scope, ...traceFilters, limit: 25 }),
      ])
        .then(([services, names, points, list]) => {
          if (cancelled) return
          setOverview(services)
          setMetricNames(names)
          setSeries(points)
          setTraces(list)
          setError(null)
        })
        .catch((problem) => !cancelled && setError(problem.message))
    }
    load()
    const timer = setInterval(load, 5000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, windowMinutes, chart, traceFilters])

  async function showTrace(traceId) {
    if (openTrace?.trace_id === traceId) {
      setOpenTrace(null)
      return
    }
    try {
      setOpenTrace(await getTrace(traceId))
    } catch (problem) {
      setError(problem.message)
    }
  }

  const services = overview?.services || []

  return (
    <>
      <header className="page-header with-action">
        <div>
          <h1 className="page-title">Telemetry</h1>
          <p>
            OpenTelemetry traces and metrics from <strong>{project ? project.name : 'all projects'}</strong>, received
            over OTLP and updated every 5 seconds.
          </p>
        </div>
        <div className="segmented light" aria-label="Time window">
          {WINDOWS.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={windowMinutes === minutes ? 'active' : ''}
              onClick={() => setWindowMinutes(minutes)}
            >
              {minutes} min
            </button>
          ))}
        </div>
      </header>

      {error && <p className="notice bad">Could not load telemetry: {error}</p>}

      {overview && services.length === 0 && (
        <section className="glass card">
          <p className="empty">
            No telemetry in the last {windowMinutes} minutes. Start the demo shop on the Services page: its three
            programs send traces and metrics here. Any OpenTelemetry SDK can send to <code>/v1/traces</code>,{' '}
            <code>/v1/metrics</code> and <code>/v1/logs</code>.
          </p>
        </section>
      )}

      <div className="telemetry-grid">
        {services.map((service) => (
          <article key={service.service} className={`glass card telemetry-card ${service.error_rate >= 0.2 ? 'is-bad' : ''}`}>
            <div className="service-head">
              <h3>{service.service}</h3>
              <span className={`health-chip ${service.error_rate >= 0.2 ? 'bad' : service.requests ? 'good' : ''}`}>
                {service.requests ? `${percent(service.error_rate)} errors` : 'no requests'}
              </span>
            </div>
            <dl className="telemetry-facts">
              <div><dt>Requests / min</dt><dd>{service.requests_per_minute}</dd></div>
              <div><dt>Errors</dt><dd>{service.errors} of {service.requests}</dd></div>
              <div><dt>Latency p50</dt><dd>{ms(service.latency_ms.p50)}</dd></div>
              <div><dt>Latency p95</dt><dd className={service.latency_ms.p95 >= 1000 ? 'text-bad' : ''}>{ms(service.latency_ms.p95)}</dd></div>
              <div><dt>Latency p99</dt><dd>{ms(service.latency_ms.p99)}</dd></div>
              <div><dt>CPU</dt><dd>{service.cpu_percent === null ? '-' : `${service.cpu_percent}%`}</dd></div>
              <div><dt>Peak memory</dt><dd>{service.memory_mb === null ? '-' : `${service.memory_mb} MB`}</dd></div>
            </dl>
          </article>
        ))}
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Metric over time</h3>
            <p className="muted">Pick any received metric, or one calculated from the spans.</p>
          </div>
        </div>
        <div className="chart-controls">
          <select className="input" value={chart.metric} onChange={(event) => setChart({ ...chart, metric: event.target.value })}>
            {metricNames.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.kind})
              </option>
            ))}
          </select>
          <select className="input" value={chart.service} onChange={(event) => setChart({ ...chart, service: event.target.value })}>
            <option value="">All services</option>
            {services.map((service) => (
              <option key={service.service}>{service.service}</option>
            ))}
          </select>
          <select className="input" value={chart.aggregation} onChange={(event) => setChart({ ...chart, aggregation: event.target.value })}>
            {AGGREGATIONS.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <select className="input" value={chart.step_seconds} onChange={(event) => setChart({ ...chart, step_seconds: Number(event.target.value) })}>
            {[10, 30, 60, 300].map((seconds) => (
              <option key={seconds} value={seconds}>every {seconds} s</option>
            ))}
          </select>
        </div>
        {series && <LineChart points={series.points} format={formatterFor(series)} />}
      </section>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Traces</h3>
            <p className="muted">Every request, across services. Click one to see each step.</p>
          </div>
        </div>
        <div className="chart-controls">
          <select className="input" value={traceFilters.status} onChange={(event) => setTraceFilters({ ...traceFilters, status: event.target.value })}>
            <option value="ANY">All requests</option>
            <option value="ERROR">Failed only</option>
            <option value="OK">Successful only</option>
          </select>
          <select className="input" value={traceFilters.service} onChange={(event) => setTraceFilters({ ...traceFilters, service: event.target.value })}>
            <option value="">Any service</option>
            {services.map((service) => (
              <option key={service.service}>{service.service}</option>
            ))}
          </select>
          <input
            className="input"
            type="number"
            min="0"
            placeholder="Slower than (ms)"
            value={traceFilters.min_duration_ms}
            onChange={(event) => setTraceFilters({ ...traceFilters, min_duration_ms: event.target.value })}
          />
        </div>

        {traces.length === 0 ? (
          <p className="empty">No traces match.</p>
        ) : (
          <div className="table-wrap">
            <table className="log-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Request</th>
                  <th>Services</th>
                  <th>Duration</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((trace) => (
                  <Fragment key={trace.trace_id}>
                    <tr className={openTrace?.trace_id === trace.trace_id ? 'open' : ''} onClick={() => showTrace(trace.trace_id)}>
                      <td className="cell-time">{new Date(trace.start_time).toLocaleTimeString()}</td>
                      <td className="cell-service">{trace.root}</td>
                      <td>{trace.services.join(' → ')}</td>
                      <td className={trace.duration_ms >= 1000 ? 'text-bad' : ''}>{trace.duration_ms.toFixed(0)} ms</td>
                      <td>
                        {trace.error ? <span className="badge badge-error">{trace.first_error}</span> : <span className="badge badge-info">OK</span>}
                      </td>
                    </tr>
                    {openTrace?.trace_id === trace.trace_id && (
                      <tr className="raw-row">
                        <td colSpan={5}>
                          <p className="raw-label">Trace {trace.trace_id}</p>
                          <TraceWaterfall trace={openTrace} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

export default Telemetry

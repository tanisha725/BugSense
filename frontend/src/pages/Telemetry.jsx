import { Fragment, useEffect, useState } from 'react'
import LineChart from '../components/LineChart.jsx'
import TraceWaterfall from '../components/TraceWaterfall.jsx'
import {
  getMetricNames,
  getMetricSeries,
  getTelemetryRange,
  getTelemetryServices,
  getTrace,
  getTraces,
  telemetryFromLogs,
} from '../services/api.js'

// 'all' shows the whole time range of the data, for logs uploaded from the past
const WINDOWS = [5, 15, 60, 'all']

const SOURCES = {
  otel: { label: 'Measured', title: 'Sent live by the program over OpenTelemetry' },
  logs: { label: 'From logs', title: 'Calculated by BugSense from the uploaded logs' },
  both: { label: 'Measured + logs', title: 'Partly measured, partly calculated from logs' },
}
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
// For uploaded logs the same numbers are calculated from the logs themselves.
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
  const [range, setRange] = useState(null)
  const [message, setMessage] = useState(null)
  const [reloadCount, setReloadCount] = useState(0)

  // Everything refreshes every 5 seconds: telemetry is live data
  useEffect(() => {
    let cancelled = false
    async function scopeNow() {
      if (windowMinutes !== 'all') return { project_id: projectId, window_minutes: windowMinutes }
      // The whole time range of the data, which may be days or years ago
      const found = await getTelemetryRange(projectId)
      if (!cancelled) setRange(found)
      if (!found.last) return null
      return { project_id: projectId, window_minutes: Math.min(found.minutes + 2, 43200), until: found.last }
    }

    async function load() {
      let scope
      try {
        scope = await scopeNow()
      } catch (problem) {
        if (!cancelled) setError(problem.message)
        return
      }
      if (!scope) {
        if (!cancelled) {
          setOverview({ services: [] })
          setSeries(null)
          setTraces([])
        }
        return
      }
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
  }, [projectId, windowMinutes, chart, traceFilters, reloadCount])

  async function calculateFromLogs() {
    setMessage(null)
    try {
      const result = await telemetryFromLogs(projectId)
      setMessage(
        `Calculated from ${result.logs.toLocaleString()} logs: ${result.traces} traces and ` +
          `${result.metric_points} activity points.`,
      )
      setWindowMinutes('all')
      setReloadCount((count) => count + 1)
    } catch (problem) {
      setError(problem.message)
    }
  }

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
            Traces and metrics for <strong>{project ? project.name : 'all projects'}</strong>: measured live over
            OpenTelemetry, or calculated from uploaded logs. Updated every 5 seconds.
          </p>
          {windowMinutes === 'all' && range?.first && (
            <p className="muted">
              Showing all data: {new Date(range.first).toLocaleString()} → {new Date(range.last).toLocaleString()}
            </p>
          )}
        </div>
        <div className="segmented light" aria-label="Time window">
          {WINDOWS.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={windowMinutes === minutes ? 'active' : ''}
              onClick={() => setWindowMinutes(minutes)}
            >
              {minutes === 'all' ? 'All data' : `${minutes} min`}
            </button>
          ))}
        </div>
      </header>

      {error && <p className="notice bad">Could not load telemetry: {error}</p>}
      {message && <p className="notice good">{message}</p>}

      {overview && services.length === 0 && (
        <section className="glass card">
          <p className="empty">
            {windowMinutes === 'all'
              ? 'No telemetry for this project yet.'
              : `No telemetry in the last ${windowMinutes} minutes. Uploaded logs are usually from the past: try "All data".`}{' '}
            Telemetry comes from two places: programs that send it live over OpenTelemetry (start the demo shop on the
            Services page), and uploaded logs, from which BugSense calculates it.
          </p>
          {projectId && (
            <div className="form-footer">
              <span className="muted">Uploaded these logs before this feature existed?</span>
              <button type="button" className="button" onClick={calculateFromLogs}>
                Calculate telemetry from this project&apos;s logs
              </button>
            </div>
          )}
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
            <span className={`source-tag source-${service.source}`} title={SOURCES[service.source]?.title}>
              {SOURCES[service.source]?.label}
            </span>
            <dl className="telemetry-facts">
              <div><dt>Requests / min</dt><dd>{service.requests_per_minute}</dd></div>
              <div><dt>Errors</dt><dd>{service.errors} of {service.requests}</dd></div>
              <div><dt>Latency p50</dt><dd>{ms(service.latency_ms.p50)}</dd></div>
              <div><dt>Latency p95</dt><dd className={service.latency_ms.p95 >= 1000 ? 'text-bad' : ''}>{ms(service.latency_ms.p95)}</dd></div>
              <div><dt>Latency p99</dt><dd>{ms(service.latency_ms.p99)}</dd></div>
              <div><dt>CPU</dt><dd>{service.cpu_percent === null ? '-' : `${service.cpu_percent}%`}</dd></div>
              <div><dt>Peak memory</dt><dd>{service.memory_mb === null ? '-' : `${service.memory_mb} MB`}</dd></div>
              {service.log_count > 0 && (
                <>
                  <div><dt>Logs / min</dt><dd>{service.logs_per_minute}</dd></div>
                  <div>
                    <dt>Error logs</dt>
                    <dd className={service.log_error_rate >= 0.2 ? 'text-bad' : ''}>
                      {service.error_logs} of {service.log_count} ({percent(service.log_error_rate)})
                    </dd>
                  </div>
                </>
              )}
            </dl>
          </article>
        ))}
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Metric over time</h3>
            <p className="muted">
              Pick any metric: received over OpenTelemetry, calculated from the spans, or <code>log.records</code> (logs
              per minute, calculated from uploaded logs; use <em>sum</em>).
            </p>
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
                      <td className="cell-time">
                        {windowMinutes === 'all' ? new Date(trace.start_time).toLocaleString() : new Date(trace.start_time).toLocaleTimeString()}
                      </td>
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

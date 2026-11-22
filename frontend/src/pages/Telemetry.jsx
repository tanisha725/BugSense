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
import PageGuide from '../components/PageGuide.jsx'

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

// One plain sentence about a service, from the same thresholds as the alerts
// (errors: 1 in 5 requests or more; slow: p95 of 1 second or more)
function verdict(service) {
  if (!service.requests && service.log_count > 0) {
    if (service.log_error_rate >= 0.2) {
      return { tone: 'bad', text: `Problem: ${percent(service.log_error_rate)} of its log lines are errors.` }
    }
    return { tone: 'good', text: `Looks healthy: ${service.error_logs} error lines out of ${service.log_count}.` }
  }
  if (!service.requests) return { tone: 'neutral', text: 'No requests in this time window.' }
  if (service.error_rate >= 0.2) {
    return {
      tone: 'bad',
      text: `Problem: ${service.errors} of ${service.requests} requests failed (${percent(service.error_rate)}).`,
    }
  }
  if (service.latency_ms.p95 >= 1000) {
    return { tone: 'bad', text: `Slow: the slowest 5% of requests take ${ms(service.latency_ms.p95)} or more.` }
  }
  return {
    tone: 'good',
    text: `Healthy: ${service.errors} of ${service.requests} requests failed; most answered within ${ms(service.latency_ms.p50)}.`,
  }
}

// One service: request numbers when there are requests (live, or log lines
// with request IDs), log numbers when it came from logs. Empty boxes are left out.
function ServiceCard({ service }) {
  const said = verdict(service)
  const hasRequests = service.requests > 0
  const hasLogs = service.log_count > 0
  let chip = { tone: '', text: 'no data' }
  if (hasRequests) chip = { tone: service.error_rate >= 0.2 ? 'bad' : 'good', text: `${percent(service.error_rate)} errors` }
  else if (hasLogs) chip = { tone: service.log_error_rate >= 0.2 ? 'bad' : 'good', text: `${percent(service.log_error_rate)} error logs` }

  return (
    <article className={`glass card telemetry-card ${said.tone === 'bad' ? 'is-bad' : ''}`}>
      <div className="service-head">
        <h3>{service.service}</h3>
        <span className={`health-chip ${chip.tone}`}>{chip.text}</span>
      </div>
      <span className={`source-tag source-${service.source}`} title={SOURCES[service.source]?.title}>
        {SOURCES[service.source]?.label}
      </span>
      <p className={`service-verdict ${said.tone}`}>{said.text}</p>
      <dl className="telemetry-facts">
        {hasRequests && (
          <>
            <div><dt>Requests / min</dt><dd>{service.requests_per_minute}</dd></div>
            <div><dt>Errors</dt><dd>{service.errors} of {service.requests}</dd></div>
            <div><dt>Latency p50</dt><dd>{ms(service.latency_ms.p50)}</dd></div>
            <div><dt>Latency p95</dt><dd className={service.latency_ms.p95 >= 1000 ? 'text-bad' : ''}>{ms(service.latency_ms.p95)}</dd></div>
            <div><dt>Latency p99</dt><dd>{ms(service.latency_ms.p99)}</dd></div>
          </>
        )}
        {service.cpu_percent !== null && <div><dt>CPU</dt><dd>{service.cpu_percent}%</dd></div>}
        {service.memory_mb !== null && <div><dt>Peak memory</dt><dd>{service.memory_mb} MB</dd></div>}
        {hasLogs && (
          <>
            <div><dt>Log lines</dt><dd>{service.log_count.toLocaleString()}</dd></div>
            <div><dt>Logs / min</dt><dd>{service.logs_per_minute}</dd></div>
            <div>
              <dt>Error logs</dt>
              <dd className={service.log_error_rate >= 0.2 ? 'text-bad' : ''}>
                {service.error_logs.toLocaleString()} ({percent(service.log_error_rate)})
              </dd>
            </div>
          </>
        )}
      </dl>
      {!hasRequests && hasLogs && (
        <p className="muted small">
          No requests or latency: these log lines have no request IDs or durations, so BugSense counts lines and errors.
        </p>
      )}
    </article>
  )
}

// How the live data reaches this page, drawn as a strip of steps
const LIVE_STEPS = [
  ['Programs run', 'shop-web, shop-api, shop-db (or your own)'],
  ['They report', 'every few seconds, over OpenTelemetry'],
  ['BugSense stores', 'traces, metrics and logs'],
  ['This page', 'reads them again every 5 seconds'],
]

// The same idea for uploaded logs: BugSense calculates the telemetry itself
const LOG_STEPS = [
  ['You upload logs', 'on the Logs page, or import a dataset'],
  ['BugSense reads each line', 'time, service, severity, request ID, "took 120 ms"'],
  ['It builds telemetry', 'logs per minute, error share; traces when lines share a request ID'],
  ['This page', 'shows them like live data, over the logs\' own time range'],
]

function LiveFlow({ fromLogs }) {
  const steps = fromLogs ? LOG_STEPS : LIVE_STEPS
  return (
    <ol className="live-flow" aria-label="How live data gets here">
      {steps.map(([title, detail]) => (
        <li key={title}>
          <strong>{title}</strong>
          <span>{detail}</span>
        </li>
      ))}
    </ol>
  )
}

// What OpenTelemetry tells us about each service: requests, errors, latency,
// CPU and memory, a chart of any metric, and every request as a trace.
// For uploaded logs the same numbers are calculated from the logs themselves.
function Telemetry({ project, projectId }) {
  // null until chosen: live data opens on 15 minutes, uploaded (past) logs on "All data"
  const [windowMinutes, setWindowMinutes] = useState(null)
  const [autoChosen, setAutoChosen] = useState(false)
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)

  const [metricNames, setMetricNames] = useState([])
  const [chart, setChart] = useState({ service: '', metric: 'latency', aggregation: 'p95', step_seconds: 30 })
  const [series, setSeries] = useState(null)
  const [chartTouched, setChartTouched] = useState(false)

  const [traceFilters, setTraceFilters] = useState({ status: 'ANY', service: '', min_duration_ms: '' })
  const [traces, setTraces] = useState([])
  const [openTrace, setOpenTrace] = useState(null)
  const [range, setRange] = useState(null)
  const [message, setMessage] = useState(null)
  const [reloadCount, setReloadCount] = useState(0)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  // Ticks once a second, so "updated 3 s ago" stays true
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  // Picks the time window for the chosen project: uploaded logs are usually
  // from the past, so "last 15 minutes" would look empty. If the newest data is
  // older than 15 minutes, open on "All data" instead.
  useEffect(() => {
    let cancelled = false
    getTelemetryRange(projectId)
      .then((found) => {
        if (cancelled) return
        const recent = found.last && Date.now() - Date.parse(found.last) < 15 * 60 * 1000
        setWindowMinutes(recent || !found.last ? 15 : 'all')
        setAutoChosen(Boolean(found.last && !recent))
      })
      .catch(() => !cancelled && setWindowMinutes(15))
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Everything refreshes every 5 seconds: telemetry is live data
  useEffect(() => {
    if (windowMinutes === null) return undefined
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
          // Logs without requests have no latency to draw: show logs per minute instead
          const noRequests = services.services.length > 0 && services.services.every((item) => !item.requests)
          if (!chartTouched && noRequests && chart.metric === 'latency') {
            setChart({ ...chart, metric: 'log.records', aggregation: 'sum', step_seconds: 300 })
          }
          setMetricNames(names)
          setSeries(points)
          setTraces(list)
          setError(null)
          setUpdatedAt(Date.now())
        })
        .catch((problem) => !cancelled && setError(problem.message))
    }
    load()
    const timer = setInterval(load, 5000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, windowMinutes, chart, chartTouched, traceFilters, reloadCount])

  // The user picked something in the chart controls: stop choosing for them
  function changeChart(update) {
    setChartTouched(true)
    setChart({ ...chart, ...update })
  }

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
  const verdicts = services.map((service) => ({ service, ...verdict(service) }))
  const troubled = verdicts.filter((item) => item.tone === 'bad')
  const secondsAgo = updatedAt ? Math.max(0, Math.round((now - updatedAt) / 1000)) : null
  const fresh = secondsAgo !== null && secondsAgo < 15 && services.length > 0
  // Past data calculated from uploaded logs, not a live stream
  const fromLogs = windowMinutes === 'all' && services.length > 0 && services.every((item) => item.source === 'logs')

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
              {autoChosen ? 'These logs are from the past, so all their data is shown: ' : 'Showing all data: '}
              {new Date(range.first).toLocaleString()} → {new Date(range.last).toLocaleString()}
            </p>
          )}
        </div>
        <div className="segmented light" aria-label="Time window">
          {WINDOWS.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={windowMinutes === minutes ? 'active' : ''}
              onClick={() => {
                setWindowMinutes(minutes)
                setAutoChosen(false)
              }}
            >
              {minutes === 'all' ? 'All data' : `${minutes} min`}
            </button>
          ))}
        </div>
      </header>

      <PageGuide page="telemetry" />

      <section className="glass card live-card">
        <div className="live-head">
          {fromLogs ? (
            <span className="live-badge logs">FROM UPLOADED LOGS</span>
          ) : (
            <span className={`live-badge ${fresh ? 'on' : ''}`}>
              <span className="live-dot" />
              {fresh ? 'LIVE' : 'Waiting for live data'}
            </span>
          )}
          <p className="live-summary">
            {services.length === 0
              ? 'No service has reported in this time window yet.'
              : troubled.length === 0
                ? `All ${services.length} service${services.length > 1 ? 's are' : ' is'} healthy.`
                : `${troubled.length} of ${services.length} services need attention: ${troubled.map((item) => item.service.service).join(', ')}.`}
          </p>
          {secondsAgo !== null && <span className="muted small">updated {secondsAgo} s ago</span>}
        </div>
        <LiveFlow fromLogs={fromLogs} />
      </section>

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

      {services.length > 0 && (
      <div className="telemetry-grid">
        {services.map((service) => (
          <ServiceCard key={service.service} service={service} />
        ))}
      </div>
      )}

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
          <select className="input" value={chart.metric} onChange={(event) => changeChart({ metric: event.target.value })}>
            {metricNames.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.kind})
              </option>
            ))}
          </select>
          <select className="input" value={chart.service} onChange={(event) => changeChart({ service: event.target.value })}>
            <option value="">All services</option>
            {services.map((service) => (
              <option key={service.service}>{service.service}</option>
            ))}
          </select>
          <select className="input" value={chart.aggregation} onChange={(event) => changeChart({ aggregation: event.target.value })}>
            {AGGREGATIONS.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <select className="input" value={chart.step_seconds} onChange={(event) => changeChart({ step_seconds: Number(event.target.value) })}>
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
          <p className="empty">
            {services.length > 0 && services.every((item) => !item.requests)
              ? 'No traces: a trace needs log lines that share a request ID (for example req-123 or request_id=...). These logs have none, so the numbers above come from counting log lines.'
              : 'No traces match.'}
          </p>
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

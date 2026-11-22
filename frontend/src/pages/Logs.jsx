import { useEffect, useState } from 'react'
import LogForm from '../components/LogForm.jsx'
import LogTable from '../components/LogTable.jsx'
import { countLogs, deleteAllLogs, deleteLog, exportLogsUrl, getLogs } from '../services/api.js'
import PageGuide from '../components/PageGuide.jsx'

const NO_FILTERS = {
  search: '',
  severity: '',
  min_severity: '',
  service: '',
  error_type: '',
  request_id: '',
  trace_id: '',
  since: '',
  until: '',
}
const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const PAGE_SIZES = [50, 100, 200, 500]

function Logs({ project, projectId, live, onChange }) {
  const [filters, setFilters] = useState(NO_FILTERS)
  const [order, setOrder] = useState('newest')
  const [pageSize, setPageSize] = useState(100)
  const [page, setPage] = useState(0)
  const [showMore, setShowMore] = useState(false)
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  // Changing this number makes the effect below run again (used after adding logs)
  const [reloadCount, setReloadCount] = useState(0)

  const query = { ...filters, project_id: projectId }

  // Runs when the page loads, when a filter or the page changes, and every 3 seconds while live.
  useEffect(() => {
    let cancelled = false
    const current = { ...filters, project_id: projectId }
    function load() {
      Promise.all([getLogs({ ...current, order, limit: pageSize, offset: page * pageSize }), countLogs(current)])
        .then(([data, counted]) => {
          // Ignore the reply if a newer request has started since
          if (!cancelled) {
            setLogs(data)
            setTotal(counted.total)
            setError(null)
          }
        })
        .catch((problem) => {
          if (!cancelled) setError(problem.message)
        })
    }
    load()
    const timer = live ? setInterval(load, 3000) : null
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [filters, order, pageSize, page, reloadCount, projectId, live])

  function reload() {
    setReloadCount((count) => count + 1)
    onChange()
  }

  function handleDelete(id) {
    deleteLog(id)
      .then(reload)
      .catch((problem) => setError(problem.message))
  }

  function handleDeleteAll() {
    const where = project ? `in "${project.name}"` : 'in ALL projects'
    // Deleting cannot be undone, so ask first
    if (!window.confirm(`Delete every log ${where}? This cannot be undone.`)) return
    deleteAllLogs(projectId)
      .then(reload)
      .catch((problem) => setError(problem.message))
  }

  function updateFilter(name, value) {
    setFilters({ ...filters, [name]: value })
    setPage(0)
  }

  const hasFilters = Object.values(filters).some(Boolean)
  const firstShown = total === 0 ? 0 : page * pageSize + 1
  const lastShown = page * pageSize + logs.length
  const pages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <>
      <header className="page-header with-action">
        <div>
          <h1 className="page-title">Logs</h1>
          <p>
            Search everything stored in <strong>{project ? project.name : 'all projects'}</strong>
            {live && ' · updating live'}
          </p>
        </div>
        <button type="button" className="button" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Close' : '+ Add logs'}
        </button>
      </header>

      <PageGuide page="logs" />

      {showForm && <LogForm projectId={projectId} onAdded={reload} />}

      <section className="glass card">
        <div className="filters">
          <input
            className="input"
            type="search"
            placeholder="Search log text, for example 503 or req-9f31"
            value={filters.search}
            onChange={(event) => updateFilter('search', event.target.value)}
          />
          <select className="input" value={filters.severity} onChange={(event) => updateFilter('severity', event.target.value)}>
            <option value="">All severities</option>
            {LEVELS.map((level) => (
              <option key={level}>{level}</option>
            ))}
          </select>
          <input
            className="input"
            placeholder="Service name"
            value={filters.service}
            onChange={(event) => updateFilter('service', event.target.value)}
          />
          <button type="button" className="button button-quiet" onClick={() => setShowMore(!showMore)}>
            {showMore ? 'Fewer filters' : 'More filters'}
          </button>
        </div>

        {showMore && (
          <div className="filters-more">
            <label className="field">
              <span>At least</span>
              <select className="input" value={filters.min_severity} onChange={(event) => updateFilter('min_severity', event.target.value)}>
                <option value="">Any level</option>
                {LEVELS.map((level) => (
                  <option key={level}>{level}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Error type</span>
              <input className="input" placeholder="TimeoutError" value={filters.error_type} onChange={(event) => updateFilter('error_type', event.target.value)} />
            </label>
            <label className="field">
              <span>Request ID</span>
              <input className="input" placeholder="req-9f31" value={filters.request_id} onChange={(event) => updateFilter('request_id', event.target.value)} />
            </label>
            <label className="field">
              <span>Trace ID</span>
              <input className="input" placeholder="32 hex characters" value={filters.trace_id} onChange={(event) => updateFilter('trace_id', event.target.value)} />
            </label>
            <label className="field">
              <span>From</span>
              <input className="input" type="datetime-local" step="1" value={filters.since} onChange={(event) => updateFilter('since', event.target.value)} />
            </label>
            <label className="field">
              <span>To</span>
              <input className="input" type="datetime-local" step="1" value={filters.until} onChange={(event) => updateFilter('until', event.target.value)} />
            </label>
            <button
              type="button"
              className="button button-quiet"
              disabled={!hasFilters}
              onClick={() => {
                setFilters(NO_FILTERS)
                setPage(0)
              }}
            >
              Clear all
            </button>
          </div>
        )}

        <div className="table-toolbar">
          <span className="muted">
            {total === 0 ? 'No logs' : `${firstShown.toLocaleString()}–${lastShown.toLocaleString()} of ${total.toLocaleString()}`}
          </span>
          <select className="input input-small" value={order} onChange={(event) => setOrder(event.target.value)} aria-label="Order">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
          <select
            className="input input-small"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value))
              setPage(0)
            }}
            aria-label="Logs per page"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>{size} per page</option>
            ))}
          </select>
          <button type="button" className="button button-quiet button-small" disabled={page === 0} onClick={() => setPage(page - 1)}>
            ← Previous
          </button>
          <span className="muted">Page {page + 1} of {pages}</span>
          <button type="button" className="button button-quiet button-small" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
            Next →
          </button>
          <span className="spacer" />
          {/* Downloads every matching log, not only this page */}
          <a className="button button-quiet button-small" href={exportLogsUrl(query)} download>
            Export CSV
          </a>
          <button type="button" className="button button-danger" disabled={total === 0 && !hasFilters} onClick={handleDeleteAll}>
            Delete all
          </button>
        </div>

        {error ? (
          <p className="notice bad">Could not load logs: {error}</p>
        ) : (
          <LogTable
            logs={logs}
            onDelete={handleDelete}
            emptyText={hasFilters ? 'No logs match these filters.' : 'No logs yet. Add some, or import a dataset.'}
          />
        )}
      </section>
    </>
  )
}

export default Logs

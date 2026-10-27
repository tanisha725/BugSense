import { useEffect, useState } from 'react'
import LogForm from '../components/LogForm.jsx'
import LogTable from '../components/LogTable.jsx'
import { deleteAllLogs, deleteLog, exportLogsUrl, getLogs } from '../services/api.js'

const NO_FILTERS = { search: '', severity: '', service: '' }

function Logs({ project, projectId, live, onChange }) {
  const [filters, setFilters] = useState(NO_FILTERS)
  const [logs, setLogs] = useState([])
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  // Changing this number makes the effect below run again (used after adding logs)
  const [reloadCount, setReloadCount] = useState(0)

  // Runs when the page loads, when a filter changes, and every 3 seconds while live.
  useEffect(() => {
    let cancelled = false
    function load() {
      getLogs({ ...filters, project_id: projectId })
        .then((data) => {
          // Ignore the reply if a newer request has started since
          if (!cancelled) {
            setLogs(data)
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
  }, [filters, reloadCount, projectId, live])

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
  }

  const hasFilters = filters.search || filters.severity || filters.service

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
          <select
            className="input"
            value={filters.severity}
            onChange={(event) => updateFilter('severity', event.target.value)}
          >
            <option value="">All severities</option>
            <option>DEBUG</option>
            <option>INFO</option>
            <option>WARNING</option>
            <option>ERROR</option>
            <option>CRITICAL</option>
          </select>
          <input
            className="input"
            placeholder="Service name"
            value={filters.service}
            onChange={(event) => updateFilter('service', event.target.value)}
          />
          <button
            type="button"
            className="button button-quiet"
            disabled={!hasFilters}
            onClick={() => setFilters(NO_FILTERS)}
          >
            Clear
          </button>
        </div>

        <div className="table-toolbar">
          <span className="muted">
            {logs.length} shown{logs.length === 100 ? ' (newest 100)' : ''}
          </span>
          <span className="spacer" />
          {/* Downloads every matching log, not only the 100 shown */}
          <a className="button button-quiet button-small" href={exportLogsUrl({ ...filters, project_id: projectId })} download>
            Export CSV
          </a>
          <button
            type="button"
            className="button button-danger"
            disabled={logs.length === 0 && !hasFilters}
            onClick={handleDeleteAll}
          >
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

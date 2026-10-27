import { useEffect, useState } from 'react'
import IncidentRow from '../components/IncidentRow.jsx'
import { detectIncidents, getIncidentSummary, getIncidents } from '../services/api.js'

const FILTERS = [
  { status: 'OPEN', label: 'Active' },
  { status: 'RESOLVED', label: 'Resolved' },
  { status: 'ALL', label: 'All' },
]

const LEVELS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

function Incidents({ project, projectId, live }) {
  const [status, setStatus] = useState('OPEN')
  const [incidents, setIncidents] = useState(null)
  const [summary, setSummary] = useState(null)
  const [reloadCount, setReloadCount] = useState(0)
  const [message, setMessage] = useState(null)

  // Loads the list, and keeps it fresh every 3 seconds while a live stream runs
  useEffect(() => {
    let cancelled = false
    function load() {
      Promise.all([getIncidents(projectId, status), getIncidentSummary(projectId)])
        .then(([list, counts]) => {
          if (!cancelled) {
            setIncidents(list)
            setSummary(counts)
          }
        })
        .catch((problem) => !cancelled && setMessage(problem.message))
    }
    load()
    const timer = live ? setInterval(load, 3000) : null
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, status, live, reloadCount])

  async function handleDetect() {
    const result = await detectIncidents(projectId)
    setMessage(`Detection finished: ${result.open_incidents} open incidents.`)
    setReloadCount((count) => count + 1)
  }

  return (
    <>
      <header className="page-header with-action">
        <div>
          <h1 className="page-title">Incidents</h1>
          <p>
            Related failures grouped together in <strong>{project ? project.name : 'all projects'}</strong>
            {live && ' · updating live'}
          </p>
        </div>
        <button type="button" className="button button-quiet" onClick={handleDetect}>
          Run detection again
        </button>
      </header>

      <div className="incident-summary">
        <div className="glass card summary-total">
          <p className="eyebrow">Open incidents</p>
          <p className="stat-value">{summary?.open ?? '-'}</p>
        </div>
        {LEVELS.map((level) => (
          <div key={level} className={`glass card summary-level sev-${level.toLowerCase()}`}>
            <span className={`badge badge-${level.toLowerCase()}`}>{level}</span>
            <p className="stat-value">{summary?.by_severity?.[level] ?? 0}</p>
          </div>
        ))}
      </div>

      <section className="glass card">
        <div className="card-header">
          <div className="segmented light">
            {FILTERS.map((filter) => (
              <button
                key={filter.status}
                type="button"
                className={status === filter.status ? 'active' : ''}
                onClick={() => setStatus(filter.status)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {message && <p className="notice good">{message}</p>}
        </div>

        {incidents === null ? (
          <p className="empty">Loading incidents...</p>
        ) : incidents.length === 0 ? (
          <p className="empty">
            {status === 'OPEN' ? 'No active incidents. Everything looks healthy.' : 'Nothing here yet.'}
          </p>
        ) : (
          <div className="incident-list">
            {incidents.map((incident) => (
              <IncidentRow key={incident.id} incident={incident} />
            ))}
          </div>
        )}
      </section>

      <p className="footnote">
        How incidents are found: problem logs (warnings and errors) that happen within 10 minutes of each other are
        grouped together. A group becomes an incident when it has a CRITICAL log, at least 3 errors, or at least 10
        warnings.
      </p>
    </>
  )
}

export default Incidents

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import BarList from '../components/BarList.jsx'
import LogTable from '../components/LogTable.jsx'
import StatCard from '../components/StatCard.jsx'
import { getIncident, setIncidentStatus } from '../services/api.js'
import { formatDuration, formatMoment } from '../services/format.js'

const SEVERITY_RULES = [
  ['CRITICAL', 'any CRITICAL log, or errors in 3 or more services'],
  ['HIGH', '20 or more errors, or errors in 2 services'],
  ['MEDIUM', '3 or more errors'],
  ['LOW', 'only warnings (10 or more)'],
]

// One incident and all of its evidence.
function IncidentDetail({ live }) {
  const { id } = useParams()
  const [incident, setIncident] = useState(null)
  const [error, setError] = useState(null)
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    function load() {
      getIncident(id)
        .then((data) => !cancelled && setIncident(data))
        .catch((problem) => !cancelled && setError(problem.message))
    }
    load()
    const timer = live ? setInterval(load, 3000) : null
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [id, live, reloadCount])

  async function toggleStatus() {
    await setIncidentStatus(id, incident.status === 'OPEN' ? 'RESOLVED' : 'OPEN')
    setReloadCount((count) => count + 1)
  }

  if (error) {
    return (
      <p className="notice bad">
        Could not load this incident: {error}. It may have been rebuilt by detection. <Link to="/incidents">Back to incidents</Link>
      </p>
    )
  }
  if (!incident) return <p className="empty">Loading incident...</p>

  const severity = incident.severity.toLowerCase()

  return (
    <>
      <header className="page-header">
        <Link to="/incidents" className="back-link">
          ← All incidents
        </Link>
        <div className="incident-heading">
          <span className={`badge badge-${severity} badge-large`}>{incident.severity}</span>
          <span className={`status-tag ${incident.status.toLowerCase()}`}>{incident.status}</span>
          <span className="muted">Incident #{incident.id} · {incident.project_name}</span>
        </div>
        <h1 className="incident-page-title">{incident.title}</h1>
        <div className="detail-actions">
          <span className="muted">
            {formatMoment(incident.first_seen)} → {formatMoment(incident.last_seen)}
          </span>
          <span className="spacer" />
          <button type="button" className="button" onClick={toggleStatus}>
            {incident.status === 'OPEN' ? 'Mark as resolved' : 'Reopen'}
          </button>
        </div>
      </header>

      <div className="detail-stats">
        <StatCard label="Errors" value={incident.error_count} note="ERROR and CRITICAL logs" tone="bad" />
        <StatCard label="Warnings" value={incident.warning_count} note="In the same time window" tone="warn" />
        <StatCard
          label="Services"
          value={incident.service_count}
          note={`Most affected: ${incident.affected_service || 'unknown'}`}
        />
        <StatCard
          label="Duration"
          value={formatDuration(incident.first_seen, incident.last_seen)}
          note={`${incident.log_count.toLocaleString()} logs in total`}
        />
      </div>

      <div className="detail-grid">
        <section className={`card dark why-card sev-${severity}`}>
          <p className="eyebrow">Why {incident.severity}?</p>
          <ul className="why-list">
            {incident.severity_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <ul className="rule-list">
            {SEVERITY_RULES.map(([level, rule]) => (
              <li key={level} className={level === incident.severity ? 'is-current' : ''}>
                <strong>{level}</strong> {rule}
              </li>
            ))}
          </ul>
        </section>

        <section className="glass card">
          <div className="card-header">
            <h3>Services involved</h3>
            <ul className="legend-row small">
              <li><span className="swatch fill-error" />Errors</li>
              <li><span className="swatch fill-other" />Other</li>
            </ul>
          </div>
          <BarList
            items={incident.services.map((item) => ({ label: item.service, value: item.count, part: item.errors }))}
            emptyText="No services."
          />
        </section>

        <section className="glass card">
          <div className="card-header">
            <h3>What went wrong</h3>
          </div>
          <BarList
            items={incident.signatures.map((item) => ({ label: item.label, value: item.count, part: item.count }))}
            emptyText="No errors."
          />
        </section>
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Evidence, in time order</h3>
            <p className="muted">
              The logs that make up this incident. The first failure is at the top
              {incident.log_count > incident.logs.length && ` (showing the first ${incident.logs.length})`}.
            </p>
          </div>
        </div>
        <LogTable logs={incident.logs} emptyText="No logs." />
      </section>
    </>
  )
}

export default IncidentDetail

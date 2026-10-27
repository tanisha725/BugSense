import { Link } from 'react-router-dom'
import { formatDuration, formatMoment } from '../services/format.js'

// One incident in a list: severity, title, what is affected and when.
function IncidentRow({ incident, compact = false }) {
  const others = incident.service_count - 1

  return (
    <Link to={`/incidents/${incident.id}`} className={`incident-row sev-${incident.severity.toLowerCase()}`}>
      <span className={`badge badge-${incident.severity.toLowerCase()}`}>{incident.severity}</span>
      <span className="incident-main">
        <span className="incident-title">{incident.title}</span>
        <span className="incident-meta">
          {incident.affected_service || 'unknown service'}
          {others > 0 && ` +${others} more`}
          {' · '}
          {incident.error_count.toLocaleString()} errors
          {incident.warning_count > 0 && `, ${incident.warning_count.toLocaleString()} warnings`}
          {!compact && ` · ${formatMoment(incident.first_seen)} · lasted ${formatDuration(incident.first_seen, incident.last_seen)}`}
        </span>
      </span>
      {!compact && <span className={`status-tag ${incident.status.toLowerCase()}`}>{incident.status}</span>}
    </Link>
  )
}

export default IncidentRow

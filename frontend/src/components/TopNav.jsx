import { NavLink } from 'react-router-dom'

const PAGES = [
  { path: '/', label: 'Overview' },
  { path: '/incidents', label: 'Incidents' },
  { path: '/services', label: 'Services' },
  { path: '/logs', label: 'Logs' },
  { path: '/datasets', label: 'Datasets' },
]

// The floating bar at the top: logo, page links, project picker and status.
function TopNav({ health, projects, projectId, onProjectChange, stream, criticalIncidents }) {
  const allGood = health?.backend === 'online' && health?.database === 'connected'

  let status = { tone: 'neutral', text: 'Checking...' }
  if (stream?.running) status = { tone: 'live', text: `Live · ${stream.sent} lines` }
  else if (health && !allGood) status = { tone: 'bad', text: 'Needs attention' }
  else if (criticalIncidents > 0) {
    status = { tone: 'bad', text: `${criticalIncidents} critical incident${criticalIncidents > 1 ? 's' : ''}` }
  } else if (health) status = { tone: 'good', text: 'All systems normal' }

  return (
    <header className="topnav">
      <div className="brand">
        <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="10" fill="#111113" />
          <path
            d="M6 17h5l2.5-7 4 13 2.5-6h6"
            fill="none"
            stroke="#fff"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div>
          <p className="brand-name">BugSense</p>
          <p className="brand-tagline">Incident analysis</p>
        </div>
      </div>

      <nav className="nav-pills" aria-label="Pages">
        {PAGES.map((page) => (
          <NavLink key={page.path} to={page.path} end={page.path === '/'} className="nav-pill">
            {page.label}
          </NavLink>
        ))}
      </nav>

      <div className="topnav-right">
        <label className="project-picker">
          <span className="sr-only">Project</span>
          <select
            value={projectId ?? ''}
            onChange={(event) => onProjectChange(Number(event.target.value) || null)}
          >
            <option value="">All projects</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name} ({project.log_count.toLocaleString()})
              </option>
            ))}
          </select>
        </label>
        <span className={`status-pill ${status.tone}`}>
          <span className={`dot ${status.tone}`} />
          {status.text}
        </span>
      </div>
    </header>
  )
}

export default TopNav

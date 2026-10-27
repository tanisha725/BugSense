// The dark "System pulse" card: the brain-and-heart picture with a beating glow,
// plus whether the backend, the database and a live stream are running.
function PulseCard({ health, project, live }) {
  const backendOnline = health?.backend === 'online'
  const databaseConnected = health?.database === 'connected'

  return (
    <section className="card dark pulse-card">
      <div className="pulse-art" aria-hidden="true">
        <span className="pulse-glow" />
      </div>

      <div className="pulse-top">
        <p className="eyebrow">System pulse</p>
        {live && (
          <span className="live-badge">
            <span className="dot live" /> Live
          </span>
        )}
      </div>

      <div className="pulse-bottom">
        <h2>{project ? project.name : 'All projects'}</h2>
        <ul className="pulse-status">
          <li>
            <span className={`dot ${health === null ? 'neutral' : backendOnline ? 'good' : 'bad'}`} />
            Backend {health === null ? '...' : backendOnline ? 'online' : 'offline'}
          </li>
          <li>
            <span className={`dot ${health === null ? 'neutral' : databaseConnected ? 'good' : 'bad'}`} />
            Database {health === null ? '...' : databaseConnected ? 'connected' : 'unavailable'}
          </li>
        </ul>
      </div>
    </section>
  )
}

export default PulseCard

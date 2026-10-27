import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ActivityChart from '../components/ActivityChart.jsx'
import BarList from '../components/BarList.jsx'
import PulseCard from '../components/PulseCard.jsx'
import RingGauge from '../components/RingGauge.jsx'
import SeverityBreakdown from '../components/SeverityBreakdown.jsx'
import StatCard from '../components/StatCard.jsx'
import IncidentRow from '../components/IncidentRow.jsx'
import { getIncidentSummary, getIncidents, getLogStats, getTimeline } from '../services/api.js'

function Dashboard({ health, project, projectId, live }) {
  const [stats, setStats] = useState(null)
  const [slots, setSlots] = useState([])
  const [incidents, setIncidents] = useState([])
  const [incidentCounts, setIncidentCounts] = useState(null)

  // Loads everything for the chosen project. While a live stream runs it
  // repeats every 3 seconds, and the chart shows only the last 5 minutes.
  useEffect(() => {
    let cancelled = false
    function load() {
      Promise.all([
        getLogStats(projectId),
        getTimeline(projectId, live ? 5 : undefined),
        getIncidents(projectId, 'OPEN'),
        getIncidentSummary(projectId),
      ])
        .then(([newStats, newSlots, openIncidents, counts]) => {
          if (cancelled) return
          setStats(newStats)
          setSlots(newSlots)
          setIncidents(openIncidents.slice(0, 4))
          setIncidentCounts(counts)
        })
        .catch(() => {})
    }
    load()
    const timer = live ? setInterval(load, 3000) : null
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, live])

  const total = stats?.total ?? 0
  const errorRate = total ? (stats.errors / total) * 100 : 0
  const warningRate = total ? (stats.warnings / total) * 100 : 0

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Overview</h1>
        <p>
          Health and activity for <strong>{project ? project.name : 'all projects'}</strong>
          {live && ' · updating live'}
        </p>
      </header>

      <div className="bento">
        <div className="area-pulse">
          <PulseCard health={health} project={project} live={live} />
        </div>

        <div className="area-kpis">
          <StatCard label="Total logs" value={total} note="Stored for this view" />
          <StatCard label="Errors" value={stats?.errors ?? 0} note="ERROR and CRITICAL" tone="bad" />
          <StatCard label="Warnings" value={stats?.warnings ?? 0} note="Possible problems" tone="warn" />
          <StatCard
            label="Open incidents"
            value={incidentCounts?.open ?? 0}
            note={`${incidentCounts?.critical ?? 0} critical`}
            tone={incidentCounts?.critical ? 'bad' : 'neutral'}
          />
        </div>

        <section className="glass card area-rings">
          <p className="eyebrow">Health</p>
          <div className="rings">
            <RingGauge percent={errorRate} label="Error rate" tone="bad" />
            <RingGauge percent={warningRate} label="Warning rate" tone="warn" />
          </div>
          <p className="stat-note">Share of all logs in this view.</p>
        </section>

        <section className="glass card area-activity">
          <div className="card-header">
            <h3>Activity over time</h3>
            <span className="muted">{live ? 'Last 5 minutes' : 'Whole time range'}</span>
          </div>
          {/* A new key when switching to live makes React build a fresh chart */}
          <ActivityChart key={live ? 'live' : 'history'} slots={slots} />
        </section>

        <section className="glass card area-severity">
          <div className="card-header">
            <h3>Logs by severity</h3>
          </div>
          {total ? (
            <SeverityBreakdown bySeverity={stats.by_severity} total={total} />
          ) : (
            <p className="empty">Nothing to show yet.</p>
          )}
        </section>

        <section className="glass card area-errors">
          <div className="card-header">
            <h3>Top error types</h3>
          </div>
          <BarList
            items={(stats?.top_errors ?? []).map((item) => ({ label: item.error_type, value: item.count, part: item.count }))}
            emptyText="No named error types found."
          />
        </section>

        <section className="glass card area-services">
          <div className="card-header">
            <h3>Busiest services</h3>
            <ul className="legend-row small">
              <li><span className="swatch fill-error" />Errors</li>
              <li><span className="swatch fill-other" />Other</li>
            </ul>
          </div>
          <BarList
            items={(stats?.top_services ?? []).map((item) => ({ label: item.service, value: item.count, part: item.errors }))}
            emptyText="No services found."
          />
        </section>

        <section className="card dark area-latest">
          <div className="card-header">
            <h3>Active incidents</h3>
            <Link to="/incidents" className="link-light">View all</Link>
          </div>
          {incidents.length === 0 ? (
            <p className="empty">No active incidents. Nice.</p>
          ) : (
            <div className="incident-list on-dark">
              {incidents.map((incident) => (
                <IncidentRow key={incident.id} incident={incident} compact />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  )
}

export default Dashboard

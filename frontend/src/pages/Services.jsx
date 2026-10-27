import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  controlService,
  deleteAllLogs,
  getMonitor,
  runScenario,
  startAllServices,
  stopAllServices,
} from '../services/api.js'

const STATUS_TEXT = {
  running: 'Running',
  stopped: 'Stopped',
  crashed: 'Crashed',
  'crash-loop': 'Crash loop',
}

const SCENARIO_TITLES = {
  'database-down': 'Database goes down',
  'crash-loop': 'Crash loop',
  slow: 'Slow API, error spike',
  'bad-config': 'Wrong configuration',
  recover: 'Recover everything',
}

function formatUptime(seconds) {
  if (seconds === null) return '-'
  if (seconds < 60) return `${seconds} s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
  return `${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`
}

function healthText(service) {
  if (service.port === null) return 'No health page'
  if (service.healthy === null) return 'Health unknown'
  return service.healthy ? 'Healthy' : 'Unhealthy'
}

// The demo shop: three programs that BugSense starts and watches.
function Services({ onProjectChange }) {
  const navigate = useNavigate()
  const [monitor, setMonitor] = useState(null)
  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState(null)

  // Ask for fresh status every 2 seconds
  useEffect(() => {
    let cancelled = false
    function load() {
      getMonitor()
        .then((data) => !cancelled && setMonitor(data))
        .catch((problem) => !cancelled && setMessage(problem.message))
    }
    load()
    const timer = setInterval(load, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  // Runs one action, shows "busy" on its button, then shows the new status
  async function act(label, action) {
    setBusy(label)
    setMessage(null)
    try {
      const result = await action()
      if (result?.services) setMonitor(result)
    } catch (problem) {
      setMessage(problem.message)
    } finally {
      setBusy(null)
    }
  }

  async function clearDemoLogs() {
    if (!monitor?.project_id) return
    if (!window.confirm('Delete all logs and incidents of the demo shop?')) return
    await act('clear', () => deleteAllLogs(monitor.project_id))
    setMessage('Demo logs cleared. Run the next scenario.')
  }

  function openIncidents() {
    onProjectChange(monitor.project_id)
    navigate('/incidents')
  }

  if (!monitor) return <p className="empty">Loading services...</p>

  const byName = Object.fromEntries(monitor.services.map((service) => [service.name, service]))
  const chain = ['shop-web', 'shop-api', 'shop-db']

  return (
    <>
      <header className="page-header with-action">
        <div>
          <h1 className="page-title">Services</h1>
          <p>
            A small demo shop of three programs, started and watched by BugSense. No Docker needed.
          </p>
        </div>
        <div className="header-buttons">
          <button type="button" className="button button-quiet" disabled={busy !== null} onClick={() => act('stop', stopAllServices)}>
            Stop all
          </button>
          <button type="button" className="button" disabled={busy !== null} onClick={() => act('start', startAllServices)}>
            {busy === 'start' ? 'Starting...' : 'Start all'}
          </button>
        </div>
      </header>

      {/* How a checkout travels through the shop */}
      <section className="glass card chain">
        <p className="eyebrow">How a checkout travels</p>
        <div className="chain-row">
          {chain.map((name, index) => {
            const service = byName[name]
            return (
              <div key={name} className="chain-step">
                <span className={`chain-node status-${service.status}`}>
                  <span className={`dot ${service.status === 'running' ? (service.healthy === false ? 'bad' : 'good') : service.status === 'stopped' ? 'neutral' : 'bad'}`} />
                  {name}
                </span>
                {index < chain.length - 1 && <span className="chain-arrow">→</span>}
              </div>
            )
          })}
        </div>
        <p className="muted">Every second shop-web opens the checkout, shop-api asks shop-db, and all three log the same request ID.</p>
      </section>

      <div className="service-grid">
        {monitor.services.map((service) => (
          <article key={service.name} className={`glass card service-card status-${service.status}`}>
            <div className="service-head">
              <h3>{service.name}</h3>
              {service.port && <span className="tag mono-tag">:{service.port}</span>}
            </div>
            <p className="service-description">{service.description}</p>

            <div className="service-status">
              <span className={`status-big status-${service.status}`}>
                <span className={`dot ${service.status === 'running' ? 'good' : service.status === 'stopped' ? 'neutral' : 'live'}`} />
                {STATUS_TEXT[service.status]}
              </span>
              <span className={`health-chip ${service.healthy === false ? 'bad' : service.healthy ? 'good' : ''}`}>
                {healthText(service)}
              </span>
            </div>

            <dl className="service-facts">
              <div><dt>PID</dt><dd>{service.pid ?? '-'}</dd></div>
              <div><dt>Uptime</dt><dd>{formatUptime(service.uptime_seconds)}</dd></div>
              <div><dt>Restarts</dt><dd>{service.restart_count}</dd></div>
              <div><dt>Last exit code</dt><dd>{service.exit_code ?? '-'}</dd></div>
            </dl>
            {service.fault && <p className="fault-note">Fault switched on: {service.fault}</p>}

            <div className="service-actions">
              <button type="button" className="button button-quiet button-small" disabled={busy !== null} onClick={() => act(service.name, () => controlService(service.name, 'start'))}>
                Start
              </button>
              <button type="button" className="button button-quiet button-small" disabled={busy !== null} onClick={() => act(service.name, () => controlService(service.name, 'stop'))}>
                Stop
              </button>
              <button type="button" className="button button-quiet button-small" disabled={busy !== null} onClick={() => act(service.name, () => controlService(service.name, 'restart'))}>
                Restart
              </button>
            </div>
          </article>
        ))}
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Failure scenarios</h3>
            <p className="muted">
              Break the shop on purpose and watch BugSense notice. Tip: clear the demo logs between scenarios, so each
              one becomes its own incident.
            </p>
          </div>
          <div className="header-buttons">
            <button type="button" className="button button-quiet button-small" disabled={!monitor.project_id || busy !== null} onClick={clearDemoLogs}>
              Clear demo logs
            </button>
            <button type="button" className="button button-small" disabled={!monitor.project_id} onClick={openIncidents}>
              See incidents →
            </button>
          </div>
        </div>
        <div className="scenario-grid">
          {monitor.scenarios.map((scenario) => (
            <div key={scenario.key} className={`scenario ${scenario.key === 'recover' ? 'is-recover' : ''}`}>
              <h4>{SCENARIO_TITLES[scenario.key] || scenario.key}</h4>
              <p>{scenario.description}</p>
              <button
                type="button"
                className={scenario.key === 'recover' ? 'button button-small' : 'button button-danger'}
                disabled={busy !== null}
                onClick={() => act(scenario.key, () => runScenario(scenario.key))}
              >
                {busy === scenario.key ? 'Running...' : scenario.key === 'recover' ? 'Recover' : 'Run scenario'}
              </button>
            </div>
          ))}
        </div>
        {message && <p className="notice good">{message}</p>}
      </section>

      <section className="card dark">
        <div className="card-header">
          <h3>Monitor events</h3>
          <span className="muted-light">What the monitor saw, newest first</span>
        </div>
        {monitor.events.length === 0 ? (
          <p className="empty">No events yet. Click Start all.</p>
        ) : (
          <ul className="event-list">
            {monitor.events.map((event, index) => (
              <li key={`${event.time}-${index}`}>
                <span className="event-time">{new Date(event.time).toLocaleTimeString()}</span>
                <span className={`badge badge-${event.severity.toLowerCase()}`}>{event.severity}</span>
                <span className="event-service">{event.service}</span>
                <span className="event-message">{event.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

export default Services

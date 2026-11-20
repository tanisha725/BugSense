import { useEffect, useState } from 'react'
import { getRootCause } from '../services/api.js'

const ROLE_TONE = {
  'probable origin': 'bad',
  affected: 'warn',
  involved: '',
}

// Phase 8: where the failure started, and how it spread.
// Every score comes with its reasons, so the ranking can be checked.
function RootCausePanel({ incidentId, live }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [showPoints, setShowPoints] = useState(false)

  useEffect(() => {
    let cancelled = false
    function load() {
      getRootCause(incidentId)
        .then((data) => !cancelled && setResult(data))
        .catch((problem) => !cancelled && setError(problem.message))
    }
    load()
    const timer = live ? setInterval(load, 5000) : null
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [incidentId, live])

  if (error) return <p className="notice bad">Could not rank the root causes: {error}</p>
  if (!result) return null

  const maximum = Math.max(...result.ranking.map((item) => item.score), 1)
  const chain = result.propagation

  return (
    <section className="glass card root-cause">
      <div className="card-header">
        <div>
          <h3>Where did it start?</h3>
          <p className="muted">
            {result.method === 'requests'
              ? `Based on ${result.requests_analysed} failed requests followed by their request IDs`
              : 'No request IDs: based on the order of errors and what they name'}
            {result.failed_traces > 0 && `, and ${result.failed_traces} failed traces`}.
          </p>
        </div>
        <span className={`tag confidence-tag confidence-${result.confidence}`}>Confidence: {result.confidence}</span>
      </div>

      {chain.length > 0 && (
        <div className="chain-spread">
          <p className="eyebrow">How the failure spread</p>
          <div className="chain-row">
            {chain.slice(0, 4).map((edge) => (
              <span key={`${edge.from}-${edge.to}`} className="spread-step">
                <strong>{edge.from}</strong> → <strong>{edge.to}</strong>
                <span className="muted"> ({edge.count}×)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <ol className="rank-list">
        {result.ranking.map((item) => (
          <li key={item.service}>
            <div className="rank-head">
              <span className="rank-service">{item.service}</span>
              <span className={`health-chip ${ROLE_TONE[item.role]}`}>{item.role}</span>
              <span className="rank-score">{item.score} pts</span>
            </div>
            <div className="bar-track">
              <span className="bar-fill" style={{ width: `${(item.score / maximum) * 100}%` }} />
            </div>
            <ul className="rank-reasons">
              {item.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>

      {result.example && (
        <div className="example-request">
          <p className="eyebrow">One failed request, step by step ({result.example.request})</p>
          <ol>
            {result.example.steps.map((step, index) => (
              <li key={step.service}>
                <strong>{index + 1}. {step.service}</strong>
                <span className="mono-small">{step.message}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      <button type="button" className="button button-quiet button-small" onClick={() => setShowPoints(!showPoints)}>
        {showPoints ? 'Hide how points are given' : 'How are points given?'}
      </button>
      {showPoints && (
        <ul className="rule-list light">
          <li><strong>{result.points.requests}</strong> failed first in the requests (shared by share of requests)</li>
          <li><strong>{result.points.named}</strong> named by errors in other services (&quot;connection to X failed&quot;)</li>
          <li><strong>{result.points.first}</strong> earliest error of the incident</li>
          <li><strong>{result.points.traces}</strong> deepest failing step in failed traces</li>
          <li><strong>{result.points.monitor}</strong> the process monitor saw it stop or crash</li>
        </ul>
      )}
    </section>
  )
}

export default RootCausePanel

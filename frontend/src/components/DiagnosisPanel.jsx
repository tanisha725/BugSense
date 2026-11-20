import { useEffect, useState } from 'react'
import { diagnoseIncident, getAiConfig, getDiagnoses } from '../services/api.js'

const ENGINES = [
  { key: 'auto', label: 'Auto' },
  { key: 'llm', label: 'AI' },
  { key: 'rules', label: 'Rules' },
]

function formatChars(value) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} K` : String(value)
}

// "Find the probable cause": runs the AI (or the rules) with the investigation
// tools, and shows the answer, the evidence it used, every tool call and the cost.
function DiagnosisPanel({ incidentId }) {
  const [engine, setEngine] = useState('auto')
  const [config, setConfig] = useState(null)
  const [diagnosis, setDiagnosis] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [showSteps, setShowSteps] = useState(false)

  // Show the latest earlier diagnosis of this incident, if there is one
  useEffect(() => {
    getAiConfig().then(setConfig).catch(() => setConfig(null))
    getDiagnoses(incidentId)
      .then((list) => setDiagnosis(list[0] || null))
      .catch(() => setDiagnosis(null))
  }, [incidentId])

  async function run() {
    setRunning(true)
    setError(null)
    try {
      setDiagnosis(await diagnoseIncident(incidentId, engine))
    } catch (problem) {
      setError(problem.message)
    } finally {
      setRunning(false)
    }
  }

  const cost = diagnosis?.cost

  return (
    <section className="card dark diagnosis">
      <div className="card-header">
        <div>
          <p className="eyebrow">Probable cause</p>
          <p className="muted-light">
            {config?.llm_available
              ? `AI: ${config.model} with ${config.tools} tools`
              : 'No AI key set: the rule-based investigator uses the same tools'}
          </p>
        </div>
        <div className="header-buttons">
          <div className="segmented" aria-label="Engine">
            {ENGINES.map((item) => (
              <button
                key={item.key}
                type="button"
                className={engine === item.key ? 'active' : ''}
                onClick={() => setEngine(item.key)}
                disabled={item.key === 'llm' && !config?.llm_available}
                title={item.key === 'llm' && !config?.llm_available ? 'Set LLM_API_KEY to use the AI' : ''}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button type="button" className="button button-light" onClick={run} disabled={running}>
            {running ? 'Investigating...' : diagnosis ? 'Diagnose again' : 'Find probable cause'}
          </button>
        </div>
      </div>

      {error && <p className="notice bad">{error}</p>}

      {!diagnosis && !error && (
        <p className="muted-light">
          BugSense will read the incident, see which service failed first, follow what the errors point at, and check
          the process monitor and the telemetry.
        </p>
      )}

      {diagnosis && (
        <div className="diagnosis-body">
          <p className="diagnosis-cause">{diagnosis.probable_cause}</p>
          <div className="diagnosis-tags">
            {diagnosis.root_service && <span className="tag">Root service: {diagnosis.root_service}</span>}
            <span className={`tag confidence-${diagnosis.confidence}`}>Confidence: {diagnosis.confidence}</span>
            <span className="tag">{diagnosis.engine === 'llm' ? `AI · ${diagnosis.model}` : 'Rules, no AI'}</span>
          </div>
          {diagnosis.note && <p className="muted-light">{diagnosis.note}</p>}

          <div className="diagnosis-columns">
            <div>
              <p className="eyebrow">Evidence</p>
              <ul className="why-list">
                {diagnosis.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="eyebrow">Suggested fixes</p>
              <ol className="fix-list">
                {diagnosis.suggested_fixes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
              {diagnosis.limitations && <p className="muted-light small">Limits: {diagnosis.limitations}</p>}
            </div>
          </div>

          <div className="cost-row">
            <span><strong>{diagnosis.steps.length}</strong> tool calls</span>
            <span><strong>{(cost.duration_ms / 1000).toFixed(1)} s</strong></span>
            <span><strong>{(cost.tokens_in + cost.tokens_out).toLocaleString()}</strong> AI tokens</span>
            <span>
              <strong>{formatChars(cost.raw_chars)}</strong> characters of raw logs →{' '}
              <strong>{formatChars(cost.evidence_chars)}</strong> of evidence
              {cost.reduction >= 1 && ` (${cost.reduction}× smaller)`}
            </span>
            <button type="button" className="link-light" onClick={() => setShowSteps(!showSteps)}>
              {showSteps ? 'Hide tool calls' : 'Show tool calls'}
            </button>
          </div>

          {showSteps && (
            <ol className="step-list">
              {diagnosis.steps.map((step, index) => (
                <li key={index} className={step.ok ? '' : 'is-error'}>
                  <span className="mono">{step.tool}</span>
                  <code>{typeof step.parameters === 'string' ? step.parameters : JSON.stringify(step.parameters)}</code>
                  {step.ok ? (
                    <span className="muted-light">{step.result_chars} chars · {step.duration_ms} ms</span>
                  ) : (
                    <span className="text-bad">{step.error}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  )
}

export default DiagnosisPanel

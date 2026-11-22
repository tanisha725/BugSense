import { useState } from 'react'

// The pitch, inside the product: how BugSense fits Huawei Cloud's incident
// workflow, what it saves developers, and a calculator a company fills in
// with its own numbers. Measured figures come from RESEARCH.md section 6.

// One incident, step by step: today (manual) and with BugSense.
// The minutes are example assumptions; the pilot measures the real ones.
const WORKFLOW = [
  {
    step: 'Alarm fires',
    today: 'AOM raises many alarms at once; the on-call engineer opens dashboards and guesses which matter.',
    todayMinutes: 10,
    bugsense: 'The alarms are already one incident, with its severity and the reason for it.',
    bugsenseMinutes: 1,
  },
  {
    step: 'Find where it started',
    today: 'Search LTS logs service by service, comparing timestamps by hand.',
    todayMinutes: 30,
    bugsense: '"Where did it start?" ranks the services: probable origin first, affected ones after.',
    bugsenseMinutes: 2,
  },
  {
    step: 'Follow the failure',
    today: 'Copy request IDs from one log search to the next; open APM traces one by one.',
    todayMinutes: 25,
    bugsense: 'One trace shows every hop (web → api → db) and marks the failing one.',
    bugsenseMinutes: 3,
  },
  {
    step: 'Form a hypothesis',
    today: 'Experience, luck, and often a call with a second team.',
    todayMinutes: 20,
    bugsense: 'Probable cause, root service and confidence, in seconds (rules) or about 10 s (AI).',
    bugsenseMinutes: 1,
  },
  {
    step: 'Check it',
    today: 'Re-run the searches to be sure.',
    todayMinutes: 10,
    bugsense: 'Read the evidence list; re-run any tool on the Tools page with one click.',
    bugsenseMinutes: 5,
  },
  {
    step: 'Fix it',
    today: 'The engineer decides and acts.',
    todayMinutes: null,
    bugsense: 'The engineer decides and acts. BugSense only reads; it never changes production.',
    bugsenseMinutes: null,
  },
]

const TODAY_TOTAL = WORKFLOW.reduce((sum, row) => sum + (row.todayMinutes || 0), 0)
const BUGSENSE_TOTAL = WORKFLOW.reduce((sum, row) => sum + (row.bugsenseMinutes || 0), 0)

const DEFAULTS = {
  incidents: 30,
  engineers: 2,
  manualMinutes: TODAY_TOTAL,
  bugsenseMinutes: BUGSENSE_TOTAL,
  hourlyCost: 40,
  currency: '$',
  aiShare: 50,
  tokensPerDiagnosis: 12000, // measured average (RESEARCH.md 6.3)
  pricePerMillion: 0, // free tier; enter a paid price to compare
  hosting: 15,
}

const MEASURED = [
  ['Rule-based diagnosis', '4 of 4 live faults: correct root service', 'under 25 ms, cost 0'],
  ['AI diagnosis', '4 of 4 live faults: correct root service', 'about 12 K tokens, about 10 s'],
  ['Root cause ranking', '4 of 4 live faults: true origin ranked first', 'instant, cost 0'],
  ['Evidence vs raw logs', 'Hadoop incident: 175 K characters of logs', 'sent to the AI as 5–9 K (19–32× less)'],
  ['Telemetry from logs', 'OpenStack: 809 requests rebuilt from log lines', 'p50 264 ms, p95 411 ms'],
]

function money(currency, value) {
  return `${currency}${Math.round(value).toLocaleString()}`
}

function NumberField({ label, help, value, onChange, min = 0, max, step = 1, suffix }) {
  return (
    <label className="calc-field">
      <span className="calc-label">{label}</span>
      <span className="calc-input">
        <input
          className="input"
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(event.target.value === '' ? '' : Number(event.target.value))}
        />
        {suffix && <span className="calc-suffix">{suffix}</span>}
      </span>
      {help && <span className="calc-help">{help}</span>}
    </label>
  )
}

function Calculator() {
  const [v, setV] = useState(DEFAULTS)
  const set = (name) => (value) => setV({ ...v, [name]: value })
  const n = (name) => Number(v[name]) || 0

  const savedMinutesPerIncident = Math.max(0, n('manualMinutes') - n('bugsenseMinutes'))
  const hoursSaved = (n('incidents') * n('engineers') * savedMinutesPerIncident) / 60
  const moneySaved = hoursSaved * n('hourlyCost')
  const aiDiagnoses = (n('incidents') * n('aiShare')) / 100
  const aiCost = (aiDiagnoses * n('tokensPerDiagnosis') * n('pricePerMillion')) / 1e6
  const runningCost = aiCost + n('hosting')
  const net = moneySaved - runningCost
  const faster = n('bugsenseMinutes') > 0 ? n('manualMinutes') / n('bugsenseMinutes') : null

  return (
    <section className="glass card">
      <div className="card-header">
        <div>
          <h3>Savings calculator</h3>
          <p className="muted">
            Put in the company&apos;s own numbers. The defaults are an example, not a promise; the 4-week pilot measures
            the real minutes.
          </p>
        </div>
        <button type="button" className="button button-quiet button-small" onClick={() => setV(DEFAULTS)}>
          Reset example
        </button>
      </div>

      <div className="calc-layout">
        <div className="calc-inputs">
          <p className="calc-group">The team</p>
          <NumberField label="Incidents per month" value={v.incidents} onChange={set('incidents')} />
          <NumberField label="Engineers on each incident" value={v.engineers} onChange={set('engineers')} min={1} />
          <NumberField
            label="Minutes to find the cause today"
            help="Steps 1–5 of the workflow above"
            value={v.manualMinutes}
            onChange={set('manualMinutes')}
            suffix="min"
          />
          <NumberField
            label="Minutes with BugSense"
            help="Mostly reading and checking the evidence"
            value={v.bugsenseMinutes}
            onChange={set('bugsenseMinutes')}
            suffix="min"
          />
          <label className="calc-field">
            <span className="calc-label">Cost of one engineer hour</span>
            <span className="calc-input">
              <select className="input calc-currency" value={v.currency} onChange={(event) => set('currency')(event.target.value)}>
                <option value="$">$</option>
                <option value="₹">₹</option>
                <option value="€">€</option>
                <option value="¥">¥</option>
              </select>
              <input className="input" type="number" min={0} value={v.hourlyCost} onChange={(event) => set('hourlyCost')(event.target.value === '' ? '' : Number(event.target.value))} />
            </span>
            <span className="calc-help">Salary plus overhead</span>
          </label>

          <p className="calc-group">Running BugSense</p>
          <NumberField
            label="Incidents that use the AI"
            help="The rest use the free rule engine"
            value={v.aiShare}
            onChange={set('aiShare')}
            max={100}
            suffix="%"
          />
          <NumberField
            label="Tokens per AI diagnosis"
            help="Measured average: about 12,000"
            value={v.tokensPerDiagnosis}
            onChange={set('tokensPerDiagnosis')}
            step={500}
          />
          <NumberField
            label={`AI price per million tokens (${v.currency})`}
            help="0 on the free tier; check the provider's current price"
            value={v.pricePerMillion}
            onChange={set('pricePerMillion')}
            step={0.05}
          />
          <NumberField
            label={`Hosting per month (${v.currency})`}
            help="One small server and a database"
            value={v.hosting}
            onChange={set('hosting')}
          />
        </div>

        <div className="calc-results">
          <div className="calc-big">
            <span className="calc-big-label">Engineer time saved</span>
            <span className="calc-big-value">{Math.round(hoursSaved).toLocaleString()} h</span>
            <span className="calc-big-note">per month · {Math.round(hoursSaved * 12).toLocaleString()} h per year</span>
          </div>
          <div className="calc-big">
            <span className="calc-big-label">Value of that time</span>
            <span className="calc-big-value">{money(v.currency, moneySaved)}</span>
            <span className="calc-big-note">per month · {money(v.currency, moneySaved * 12)} per year</span>
          </div>
          <dl className="calc-lines">
            <div>
              <dt>BugSense running cost</dt>
              <dd>
                {money(v.currency, runningCost)} / month
                <span className="muted small"> (AI {v.currency}{aiCost.toFixed(2)} + hosting)</span>
              </dd>
            </div>
            <div>
              <dt>Net saving</dt>
              <dd className={net >= 0 ? 'text-good' : 'text-bad'}>{money(v.currency, net)} / month</dd>
            </div>
            <div>
              <dt>Per incident</dt>
              <dd>
                {savedMinutesPerIncident} min sooner{faster ? `, ${faster.toFixed(1)}× faster to a first hypothesis` : ''}
              </dd>
            </div>
            <div>
              <dt>AI cost per diagnosis</dt>
              <dd>
                {v.currency}
                {((n('tokensPerDiagnosis') * n('pricePerMillion')) / 1e6).toFixed(4)}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </section>
  )
}

function Value() {
  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Why BugSense</h1>
        <p>
          For <strong>Huawei Cloud</strong> operations (SRE) teams: BugSense turns the telemetry and logs they already
          collect into one explained incident, with the probable cause and the evidence, in seconds and at almost no
          cost.
        </p>
      </header>

      <div className="value-grid">
        <article className="glass card value-card">
          <p className="value-kicker">For developers</p>
          <h3>Start from the answer, not from a search box</h3>
          <ul>
            <li>No more searching each service&apos;s logs by hand at 3 a.m.</li>
            <li>One trace shows the exact hop that failed.</li>
            <li>Every answer lists its evidence, so it can be checked in a minute.</li>
            <li>Nothing new to learn: it reads the OpenTelemetry data services already send.</li>
          </ul>
        </article>
        <article className="glass card value-card">
          <p className="value-kicker">For the company</p>
          <h3>Shorter outages, lower cost</h3>
          <ul>
            <li>Less time to find the cause means less downtime for customers.</li>
            <li>No model training, no GPUs: rules handle clear cases for free.</li>
            <li>AI cost stays at about 12 K tokens per incident, however large the logs.</li>
            <li>The model is swappable, so a Huawei-hosted one keeps data inside Huawei Cloud.</li>
          </ul>
        </article>
        <article className="glass card value-card">
          <p className="value-kicker">For trust and safety</p>
          <h3>The engineer stays in charge</h3>
          <ul>
            <li>The tools only read; BugSense never runs commands in production.</li>
            <li>Every tool call the AI made is shown and can be repeated.</li>
            <li>Confidence is stated with its reason: high, medium or low.</li>
            <li>Runs as small containers (Podman), with a backup UI.</li>
          </ul>
        </article>
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>How it fits Huawei Cloud&apos;s workflow</h3>
            <p className="muted">
              Huawei Cloud AOM and APM accept OpenTelemetry. An OpenTelemetry Collector sends one copy of the same data
              to BugSense; no service changes.
            </p>
          </div>
        </div>
        <div className="fit-flow" aria-label="Data path">
          <span className="fit-box">Services with the OpenTelemetry SDK</span>
          <span className="fit-arrow">→</span>
          <span className="fit-box">OpenTelemetry Collector</span>
          <span className="fit-arrow">→</span>
          <span className="fit-split">
            <span className="fit-box">Huawei AOM / APM: dashboards, alarms</span>
            <span className="fit-box accent">BugSense: incident, origin, probable cause</span>
          </span>
        </div>

        <div className="table-wrap">
          <table className="log-table workflow-table">
            <thead>
              <tr>
                <th>Step of one incident</th>
                <th>Today (manual)</th>
                <th>With BugSense</th>
              </tr>
            </thead>
            <tbody>
              {WORKFLOW.map((row) => (
                <tr key={row.step}>
                  <td className="cell-service">{row.step}</td>
                  <td>
                    {row.today}
                    {row.todayMinutes !== null && <span className="minutes bad">~{row.todayMinutes} min</span>}
                  </td>
                  <td>
                    {row.bugsense}
                    {row.bugsenseMinutes !== null && <span className="minutes good">~{row.bugsenseMinutes} min</span>}
                  </td>
                </tr>
              ))}
              <tr className="workflow-total">
                <td>Time to a checked hypothesis</td>
                <td>~{TODAY_TOTAL} min</td>
                <td>~{BUGSENSE_TOTAL} min</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Minutes are example assumptions to show the shape of the saving. BugSense&apos;s own steps are measured (under
          25 ms for rules, about 10 s for the AI); the engineer&apos;s reading time is not.
        </p>
      </section>

      <Calculator />

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Cost: three ways to diagnose an incident</h3>
          </div>
        </div>
        <div className="table-wrap">
          <table className="log-table">
            <thead>
              <tr>
                <th></th>
                <th>Manual triage</th>
                <th>Large AI reading the raw logs</th>
                <th>BugSense</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="cell-service">Who pays</td>
                <td>Engineer hours, every incident</td>
                <td>AI tokens, growing with log size</td>
                <td>Mostly nothing: rules first, AI only when needed</td>
              </tr>
              <tr>
                <td className="cell-service">AI input per incident</td>
                <td>-</td>
                <td>All the logs (Hadoop example: 175 K characters, about 44 K tokens)</td>
                <td>A fixed-size case file: about 12 K tokens in total</td>
              </tr>
              <tr>
                <td className="cell-service">Training</td>
                <td>Years of experience</td>
                <td>Often fine-tuning on past incidents</td>
                <td>None (zero-shot)</td>
              </tr>
              <tr>
                <td className="cell-service">Infrastructure</td>
                <td>-</td>
                <td>GPU servers or a large paid model</td>
                <td>Small containers: API, database, UI and backup UI</td>
              </tr>
              <tr>
                <td className="cell-service">Can it be checked?</td>
                <td>Depends on the engineer</td>
                <td>Often a text answer only</td>
                <td>Evidence list plus every tool call</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Measured, not promised</h3>
            <p className="muted">From the evaluation in RESEARCH.md (demo shop faults and public datasets).</p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="log-table">
            <tbody>
              {MEASURED.map(([what, result, cost]) => (
                <tr key={what}>
                  <td className="cell-service">{what}</td>
                  <td>{result}</td>
                  <td>{cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>Proposed pilot: 4 weeks</h3>
          </div>
        </div>
        <ol className="pilot-steps">
          <li><strong>Week 1:</strong> send one non-critical service&apos;s OpenTelemetry data to BugSense through the Collector.</li>
          <li><strong>Week 2:</strong> label 20 past incidents with their real cause.</li>
          <li><strong>Week 3:</strong> run the rules and the AI on all 20; measure accuracy, tokens and seconds.</li>
          <li><strong>Week 4:</strong> engineers use it on live incidents; measure the minutes to a first hypothesis against today.</li>
        </ol>
      </section>
    </>
  )
}

export default Value

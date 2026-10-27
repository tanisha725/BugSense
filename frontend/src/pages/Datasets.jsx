import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getDatasets, importDataset, startStream, stopStream } from '../services/api.js'

const SPEEDS = [1, 2, 5, 10, 20]

// Real-world log datasets: import one at once, or stream it in live.
function Datasets({ stream, onStreamChange, onProjectChange }) {
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState([])
  const [speed, setSpeed] = useState(5)
  const [busy, setBusy] = useState(null) // key of the dataset being imported
  const [message, setMessage] = useState(null)

  useEffect(() => {
    getDatasets().then(setDatasets).catch((problem) => setMessage({ ok: false, text: problem.message }))
  }, [])

  async function handleImport(dataset) {
    setBusy(dataset.key)
    setMessage(null)
    try {
      const result = await importDataset(dataset.key)
      onProjectChange(result.project_id)
      navigate('/')
    } catch (problem) {
      setMessage({ ok: false, text: problem.message })
    } finally {
      setBusy(null)
    }
  }

  async function handleStream(dataset) {
    setMessage(null)
    try {
      const status = await startStream(dataset.key, speed)
      onStreamChange(status)
      onProjectChange(status.project_id)
      navigate('/')
    } catch (problem) {
      setMessage({ ok: false, text: problem.message })
    }
  }

  async function handleStop() {
    onStreamChange(await stopStream())
  }

  const streaming = datasets.find((dataset) => dataset.key === stream?.dataset)
  const progress = stream?.total ? (stream.sent / stream.total) * 100 : 0

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Datasets</h1>
        <p>
          Real logs from six real systems, from the <strong>Loghub</strong> research collection.
          Import one to analyse it, or stream it in live.
        </p>
      </header>

      {stream?.running && streaming && (
        <section className="card dark stream-panel">
          <div>
            <p className="eyebrow">
              <span className="dot live" /> Streaming live
            </p>
            <h2>{streaming.name}</h2>
            <p className="muted-light">
              {stream.sent.toLocaleString()} of {stream.total.toLocaleString()} lines · {stream.speed} per second
            </p>
          </div>
          <div className="stream-progress" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="stream-actions">
            <button type="button" className="button button-light" onClick={() => navigate('/')}>
              Watch on Overview
            </button>
            <button type="button" className="button button-quiet-light" onClick={handleStop}>
              Stop
            </button>
          </div>
        </section>
      )}

      <div className="glass card speed-bar">
        <span>Live stream speed</span>
        <div className="segmented">
          {SPEEDS.map((value) => (
            <button
              key={value}
              type="button"
              className={value === speed ? 'active' : ''}
              onClick={() => setSpeed(value)}
            >
              {value}/s
            </button>
          ))}
        </div>
        {message && <p className={message.ok ? 'notice good' : 'notice bad'}>{message.text}</p>}
      </div>

      <div className="dataset-grid">
        {datasets.map((dataset, index) => (
          <article key={dataset.key} className="glass card dataset-card" style={{ '--i': index }}>
            <div className="dataset-head">
              <span className="dataset-icon">
                {dataset.name.split(' ').slice(0, 2).map((word) => word[0]).join('')}
              </span>
              <span className="tag">{dataset.system}</span>
            </div>
            <h3>
              <Link to={`/datasets/${dataset.key}`} className="title-link">
                {dataset.name}
              </Link>
            </h3>
            <p className="dataset-description">{dataset.description}</p>
            <pre className="dataset-sample" title={dataset.sample}>{dataset.sample}</pre>
            <div className="dataset-footer">
              <Link to={`/datasets/${dataset.key}`} className="link">
                View {dataset.lines.toLocaleString()} lines →
              </Link>
              <div className="dataset-actions">
                <button
                  type="button"
                  className="button button-quiet"
                  disabled={busy !== null}
                  onClick={() => handleImport(dataset)}
                >
                  {busy === dataset.key ? 'Importing...' : 'Import'}
                </button>
                <button type="button" className="button" onClick={() => handleStream(dataset)}>
                  Stream live
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}

export default Datasets

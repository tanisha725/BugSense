import { useState } from 'react'
import { submitLogText, submitStructuredLog, uploadLogFile } from '../services/api.js'

const TABS = [
  { id: 'text', label: 'Paste text' },
  { id: 'json', label: 'Structured' },
  { id: 'file', label: 'Upload file' },
]

const EMPTY_STRUCTURED = { message: '', severity: 'ERROR', service: '' }

// The "Add logs" box with three ways to send logs to the backend.
// onAdded is called after logs are stored so the page can refresh its list.
function LogForm({ projectId, onAdded }) {
  const [tab, setTab] = useState('text')
  const [text, setText] = useState('')
  const [structured, setStructured] = useState(EMPTY_STRUCTURED)
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null) // { ok, message }
  const [sending, setSending] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setSending(true)
    setResult(null)
    try {
      let created = 1
      let skipped = 0
      if (tab === 'text') {
        ;({ created, skipped } = await submitLogText(text, projectId))
        setText('')
      } else if (tab === 'json') {
        // Leave out the service if the box was left empty
        await submitStructuredLog({ ...structured, service: structured.service || null }, projectId)
        setStructured(EMPTY_STRUCTURED)
      } else {
        ;({ created, skipped } = await uploadLogFile(file, projectId))
        setFile(null)
        event.target.reset()
      }
      const skippedNote = skipped ? `, ${skipped} skipped` : ''
      setResult({ ok: true, message: `Added ${created} log${created === 1 ? '' : 's'}${skippedNote}.` })
      onAdded()
    } catch (error) {
      setResult({ ok: false, message: error.message })
    } finally {
      setSending(false)
    }
  }

  const canSend =
    (tab === 'text' && text.trim()) ||
    (tab === 'json' && structured.message.trim()) ||
    (tab === 'file' && file)

  return (
    <form className="glass card log-form" onSubmit={handleSubmit}>
      <div className="card-header">
        <h3>Add logs</h3>
        <div className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? 'tab active' : 'tab'}
              onClick={() => {
                setTab(item.id)
                setResult(null)
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'text' && (
        <textarea
          className="input mono"
          rows={6}
          placeholder={'2026-10-08 10:15:02 ERROR [checkout] Database connection refused\nOne log per line. Indented lines stay with the line above.'}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      )}

      {tab === 'json' && (
        <div className="field-grid">
          <label className="field">
            Severity
            <select
              className="input"
              value={structured.severity}
              onChange={(event) => setStructured({ ...structured, severity: event.target.value })}
            >
              <option>DEBUG</option>
              <option>INFO</option>
              <option>WARNING</option>
              <option>ERROR</option>
              <option>CRITICAL</option>
            </select>
          </label>
          <label className="field">
            Service
            <input
              className="input"
              placeholder="checkout-api"
              value={structured.service}
              onChange={(event) => setStructured({ ...structured, service: event.target.value })}
            />
          </label>
          <label className="field field-wide">
            Message
            <input
              className="input"
              placeholder="Database connection refused"
              value={structured.message}
              onChange={(event) => setStructured({ ...structured, message: event.target.value })}
            />
          </label>
        </div>
      )}

      {tab === 'file' && (
        <label className="dropzone">
          <input
            type="file"
            accept=".log,.txt,.json,.jsonl"
            onChange={(event) => setFile(event.target.files[0] || null)}
          />
          <span className="dropzone-title">{file ? file.name : 'Choose a log file'}</span>
          <span className="dropzone-hint">.log, .txt, .json or .jsonl, up to 2 MB</span>
        </label>
      )}

      <div className="form-footer">
        {result && <p className={result.ok ? 'notice good' : 'notice bad'}>{result.message}</p>}
        <button className="button" disabled={!canSend || sending}>
          {sending ? 'Sending...' : 'Send logs'}
        </button>
      </div>
    </form>
  )
}

export default LogForm

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import BarList from '../components/BarList.jsx'
import SeverityBreakdown from '../components/SeverityBreakdown.jsx'
import StatCard from '../components/StatCard.jsx'
import {
  datasetCsvUrl,
  datasetDownloadUrl,
  getDataset,
  getDatasetCsv,
  importDataset,
  parsedCsvUrl,
  startStream,
} from '../services/api.js'

const PAGE_SIZE = 50

function formatDate(value) {
  return value
    ? new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric' })
    : '-'
}

function formatClock(value) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// "18 Oct 2015" + "18:01 to 18:10" for one day, otherwise "4 Dec 2005" + "to 5 Jan 2006"
function timeRange(first, last) {
  if (!first) return { value: '-', note: 'No timestamps' }
  if (formatDate(first) === formatDate(last)) {
    return { value: formatDate(first), note: `${formatClock(first)} to ${formatClock(last)}` }
  }
  return { value: formatDate(first), note: `to ${formatDate(last)}` }
}

function formatTime(value) {
  return value
    ? new Date(value).toLocaleString([], {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '-'
}

// The dataset viewer: what the file is, and every line shown raw
// next to the fields BugSense's parser read out of it.
function DatasetDetail({ onStreamChange, onProjectChange }) {
  const { key } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [searchParams] = useSearchParams()
  // "raw" = the log file, "csv" = Loghub's CSV. A link ending in ?view=csv opens the CSV directly.
  const [view, setView] = useState(searchParams.get('view') === 'csv' ? 'csv' : 'raw')
  const [csvPage, setCsvPage] = useState(null)

  // Loads one page of Loghub's CSV when the CSV view is open
  useEffect(() => {
    if (view !== 'csv') return
    let cancelled = false
    getDatasetCsv(key, { search, offset, limit: PAGE_SIZE })
      .then((result) => {
        if (!cancelled) setCsvPage(result)
      })
      .catch((problem) => {
        if (!cancelled) setError(problem.message)
      })
    return () => {
      cancelled = true
    }
  }, [key, search, offset, view])

  useEffect(() => {
    let cancelled = false
    getDataset(key, { search, offset, limit: PAGE_SIZE })
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((problem) => {
        if (!cancelled) setError(problem.message)
      })
    return () => {
      cancelled = true
    }
  }, [key, search, offset])

  async function handleImport() {
    try {
      const result = await importDataset(key)
      onProjectChange(result.project_id)
      navigate('/')
    } catch (problem) {
      setError(problem.message)
    }
  }

  async function handleStream() {
    try {
      const status = await startStream(key, 10)
      onStreamChange(status)
      onProjectChange(status.project_id)
      navigate('/')
    } catch (problem) {
      setError(problem.message)
    }
  }

  if (error && !data) return <p className="notice bad">Could not load the dataset: {error}</p>
  if (!data) return <p className="empty">Loading dataset...</p>

  const recognisedPercent = (data.recognised / data.lines) * 100
  const range = timeRange(data.first_time, data.last_time)
  const matches = view === 'csv' ? (csvPage?.matches ?? 0) : data.matches
  const lastShown = Math.min(offset + PAGE_SIZE, matches)
  const verification = data.verification

  return (
    <>
      <header className="page-header">
        <Link to="/datasets" className="back-link">
          ← All datasets
        </Link>
        <h1 className="page-title">{data.name}</h1>
        <p>{data.description}</p>
        <div className="detail-actions">
          <span className="tag">{data.system}</span>
          <span className="tag mono-tag">{data.file}</span>
          <a className="link" href={data.source_url} target="_blank" rel="noreferrer">
            Source: Loghub ↗
          </a>
          <span className="spacer" />
          <a className="button button-quiet" href={datasetDownloadUrl(key)} download>
            Raw .log file
          </a>
          <a className="button button-quiet" href={datasetCsvUrl(key)} download>
            Loghub CSV
          </a>
          <a className="button button-quiet" href={parsedCsvUrl(key)} download>
            BugSense CSV
          </a>
          <button type="button" className="button button-quiet" onClick={handleImport}>
            Import
          </button>
          <button type="button" className="button" onClick={handleStream}>
            Stream live
          </button>
        </div>
      </header>

      <div className="detail-stats">
        <StatCard label="Log lines" value={data.lines} note={`${(data.file_size / 1024).toFixed(0)} KB file`} />
        <StatCard label="Time range" value={range.value} note={range.note} />
        <StatCard
          label="Format recognised"
          value={`${recognisedPercent.toFixed(0)}%`}
          note={`${data.format} format, ${data.recognised.toLocaleString()} lines`}
        />
        <StatCard label="Services" value={data.service_count} note="Different components logging" />
      </div>

      <section className="card dark verify-card">
        <div>
          <p className="eyebrow">Verification</p>
          <h2>Checked against Loghub&apos;s official CSV</h2>
          <p className="muted-light">
            Loghub&apos;s researchers published this dataset as a CSV with every line already split
            into columns. BugSense parsed the raw .log file on its own, and every line was then
            compared with the same row of the CSV.
          </p>
        </div>
        <ul className="verify-list">
          <li>
            <span>Rows</span>
            <strong>
              {verification.parsed_lines.toLocaleString()} parsed · {verification.csv_rows.toLocaleString()} in CSV
            </strong>
          </li>
          {verification.checks.map((check) => (
            <li key={check.name}>
              <span>{check.name}</span>
              <strong>
                {check.matched === check.compared ? '✓ ' : ''}
                {check.matched.toLocaleString()} / {check.compared.toLocaleString()} match (
                {((check.matched / check.compared) * 100).toFixed(1)}%)
              </strong>
            </li>
          ))}
        </ul>
      </section>

      <div className="detail-grid">
        <section className="glass card">
          <div className="card-header">
            <h3>Severity in this dataset</h3>
          </div>
          <SeverityBreakdown bySeverity={data.by_severity} total={data.lines} />
        </section>
        <section className="glass card">
          <div className="card-header">
            <h3>Top services</h3>
          </div>
          <BarList
            items={data.top_services.map((item) => ({ label: item.service, value: item.count, part: 0 }))}
            emptyText="No services found."
          />
        </section>
        <section className="glass card">
          <div className="card-header">
            <h3>Top error types</h3>
          </div>
          <BarList
            items={data.top_errors.map((item) => ({ label: item.error_type, value: item.count, part: item.count }))}
            emptyText="This dataset has no named error types."
          />
        </section>
      </div>

      <section className="glass card">
        <div className="card-header">
          <div>
            <h3>The data, line by line</h3>
            <p className="muted">
              {view === 'raw'
                ? "Left: the line exactly as it is in the .log file. Right: what BugSense's parser read out of it."
                : "Loghub's CSV exactly as published. The last column shows whether BugSense agrees with the row."}
            </p>
          </div>
          <div className="segmented light">
            <button type="button" className={view === 'raw' ? 'active' : ''} onClick={() => { setView('raw'); setOffset(0) }}>
              Raw log + parsed
            </button>
            <button type="button" className={view === 'csv' ? 'active' : ''} onClick={() => { setView('csv'); setOffset(0) }}>
              Loghub CSV
            </button>
          </div>
          <input
            className="input search-small"
            type="search"
            placeholder="Search this dataset"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setOffset(0)
            }}
          />
        </div>

        {view === 'csv' ? (
          !csvPage ? (
            <p className="empty">Loading CSV...</p>
          ) : csvPage.rows.length === 0 ? (
            <p className="empty">No rows contain “{search}”.</p>
          ) : (
            <div className="table-wrap">
              <table className="log-table csv-table">
                <thead>
                  <tr>
                    {csvPage.header.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                    <th>BugSense agrees</th>
                  </tr>
                </thead>
                <tbody>
                  {csvPage.rows.map((row) => (
                    <tr key={row.values[0]}>
                      {row.values.map((value, index) => (
                        <td key={index}>{value}</td>
                      ))}
                      <td className={row.agrees ? 'agree-yes' : 'agree-no'}>{row.agrees ? '✓ Yes' : '✗ No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : data.rows.length === 0 ? (
          <p className="empty">No lines contain “{search}”.</p>
        ) : (
          <div className="table-wrap">
            <table className="log-table dataset-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Raw line</th>
                  <th>Time</th>
                  <th>Severity</th>
                  <th>Service</th>
                  <th>Error type</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.line}>
                    <td className="cell-time">{row.line}</td>
                    <td className="cell-raw" title={row.raw}>
                      {row.raw}
                    </td>
                    <td className="cell-time">{formatTime(row.timestamp)}</td>
                    <td>
                      <span className={`badge badge-${(row.severity || 'none').toLowerCase()}`}>
                        {row.severity || '-'}
                      </span>
                    </td>
                    <td className="cell-service">{row.service || '-'}</td>
                    <td>{row.error_type ? <span className="chip">{row.error_type}</span> : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pager">
          <span className="muted">
            {matches === 0
              ? 'No lines'
              : `${view === 'csv' ? 'Rows' : 'Lines'} ${(offset + 1).toLocaleString()}–${lastShown.toLocaleString()} of ${matches.toLocaleString()}`}
          </span>
          <div className="pager-buttons">
            <button
              type="button"
              className="button button-quiet"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ← Previous
            </button>
            <button
              type="button"
              className="button button-quiet"
              disabled={lastShown >= matches}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </div>
      </section>
    </>
  )
}

export default DatasetDetail

import { Fragment, useState } from 'react'

function formatTime(value) {
  const date = new Date(value)
  return date.toLocaleString([], {
    // Old datasets are years back, so the year is shown when it is not this year
    ...(date.getFullYear() !== new Date().getFullYear() && { year: 'numeric' }),
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function SeverityBadge({ severity }) {
  if (!severity) return <span className="badge badge-none">-</span>
  return <span className={`badge badge-${severity.toLowerCase()}`}>{severity}</span>
}

// Shows logs in a table. Clicking a row opens the full raw log underneath it.
// If onDelete is given, the opened row also gets a "Delete log" button.
function LogTable({ logs, emptyText = 'No logs yet.', onDelete }) {
  const [openId, setOpenId] = useState(null)

  if (logs.length === 0) {
    return <p className="empty">{emptyText}</p>
  }

  return (
    <div className="table-wrap">
      <table className="log-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Severity</th>
            <th>Service</th>
            <th>Error type</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <Fragment key={log.id}>
              <tr
                className={openId === log.id ? 'open' : ''}
                onClick={() => setOpenId(openId === log.id ? null : log.id)}
              >
                <td className="cell-time">{formatTime(log.timestamp || log.created_at)}</td>
                <td>
                  <SeverityBadge severity={log.severity} />
                </td>
                <td className="cell-service">{log.service || '-'}</td>
                <td>
                  {log.error_type ? <span className="chip">{log.error_type}</span> : <span className="badge-none">-</span>}
                </td>
                <td className="cell-message">{log.message || log.raw}</td>
              </tr>
              {openId === log.id && (
                <tr className="raw-row">
                  <td colSpan={5}>
                    {(log.request_id || log.stack_trace) && (
                      <dl className="details">
                        {log.request_id && (
                          <div>
                            <dt>Request ID</dt>
                            <dd>{log.request_id}</dd>
                          </div>
                        )}
                        {log.stack_trace && (
                          <div>
                            <dt>Stack trace</dt>
                            <dd>{log.stack_trace.split('\n').length} lines</dd>
                          </div>
                        )}
                      </dl>
                    )}
                    <div className="raw-header">
                      <p className="raw-label">Raw log</p>
                      {onDelete && (
                        <button
                          type="button"
                          className="button button-danger"
                          onClick={() => onDelete(log.id)}
                        >
                          Delete log
                        </button>
                      )}
                    </div>
                    <pre>{log.raw}</pre>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default LogTable

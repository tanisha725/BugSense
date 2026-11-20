// One request drawn as a waterfall: each span is a bar that starts when the
// step started and is as long as it took. Indentation shows who called whom.
function TraceWaterfall({ trace }) {
  const total = Math.max(trace.duration_ms, 1)

  return (
    <div className="waterfall">
      <div className="waterfall-scale">
        <span>0 ms</span>
        <span>{(total / 2).toFixed(0)} ms</span>
        <span>{total.toFixed(0)} ms</span>
      </div>
      {trace.spans.map((span) => (
        <div key={span.span_id} className={`waterfall-row ${span.status === 'ERROR' ? 'is-error' : ''}`}>
          <div className="waterfall-label" style={{ paddingLeft: `${span.depth * 16}px` }}>
            <span className="waterfall-service">{span.service}</span>
            <span className="waterfall-name">{span.name}</span>
          </div>
          <div className="waterfall-track">
            <span
              className="waterfall-bar"
              style={{
                left: `${(span.offset_ms / total) * 100}%`,
                width: `${Math.max((span.duration_ms / total) * 100, 0.8)}%`,
              }}
              title={span.status_message || `${span.kind} span`}
            />
          </div>
          <span className="waterfall-time">{span.duration_ms.toFixed(1)} ms</span>
          {span.status === 'ERROR' && span.status_message && (
            <p className="waterfall-error" style={{ paddingLeft: `${span.depth * 16}px` }}>
              {span.status_message}
            </p>
          )}
        </div>
      ))}
      {trace.logs?.length > 0 && (
        <div className="waterfall-logs">
          <p className="eyebrow">Logs written during this request</p>
          <ul>
            {trace.logs.map((log, index) => (
              <li key={index}>
                <span className={`badge badge-${(log.severity || 'none').toLowerCase()}`}>{log.severity || '-'}</span>
                <span className="event-service">{log.service}</span>
                <span className="mono-small">{log.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default TraceWaterfall

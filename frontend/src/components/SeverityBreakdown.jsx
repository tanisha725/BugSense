// Problems first, then normal activity
const SEVERITIES = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'UNKNOWN']

// One bar split into coloured parts, plus a table with the exact numbers.
function SeverityBreakdown({ bySeverity, total }) {
  const present = SEVERITIES.filter((name) => bySeverity[name])

  return (
    <>
      <div className="split-bar" role="img" aria-label="Logs by severity">
        {present.map((name) => (
          <span
            key={name}
            className={`fill-${name.toLowerCase()}`}
            style={{ flexGrow: bySeverity[name] }}
            title={`${name}: ${bySeverity[name].toLocaleString()}`}
          />
        ))}
      </div>
      <ul className="severity-rows">
        {present.map((name) => (
          <li key={name}>
            <span className={`swatch fill-${name.toLowerCase()}`} />
            <span>{name === 'UNKNOWN' ? 'No level' : name}</span>
            <strong>{bySeverity[name].toLocaleString()}</strong>
            <span className="muted">{((bySeverity[name] / total) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </>
  )
}

export default SeverityBreakdown

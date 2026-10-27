// A circle that fills up to a percentage, like a progress ring.
function RingGauge({ percent, label, tone = 'ink' }) {
  const radius = 42
  const circumference = 2 * Math.PI * radius
  const safePercent = Math.max(0, Math.min(100, percent || 0))

  return (
    <figure className="ring">
      <svg viewBox="0 0 100 100" role="img" aria-label={`${label}: ${safePercent.toFixed(1)}%`}>
        <circle className="ring-track" cx="50" cy="50" r={radius} />
        <circle
          className={`ring-fill ring-${tone}`}
          cx="50"
          cy="50"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - safePercent / 100)}
        />
      </svg>
      <span className="ring-value">
        {safePercent < 10 ? safePercent.toFixed(1) : Math.round(safePercent)}%
      </span>
      <figcaption>{label}</figcaption>
    </figure>
  )
}

export default RingGauge

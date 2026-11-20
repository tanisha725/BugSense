import { useState } from 'react'

const WIDTH = 600
const HEIGHT = 150

// One metric over time as a line. Empty slots (no data) leave a gap.
// Hovering shows the exact value of a point.
function LineChart({ points, format = (value) => value, emptyText = 'No data in this window.' }) {
  const [hovered, setHovered] = useState(null)
  const values = points.map((point) => point.value).filter((value) => value !== null)
  if (values.length === 0) return <p className="empty">{emptyText}</p>

  const maximum = Math.max(...values) || 1
  const step = WIDTH / Math.max(points.length - 1, 1)
  const x = (index) => index * step
  const y = (value) => HEIGHT - (value / maximum) * (HEIGHT - 12) - 4

  // Lines are broken where a slot has no value
  const segments = []
  let current = []
  points.forEach((point, index) => {
    if (point.value === null) {
      if (current.length) segments.push(current)
      current = []
    } else {
      current.push([x(index), y(point.value)])
    }
  })
  if (current.length) segments.push(current)

  const shown = hovered !== null ? points[hovered] : null

  return (
    <div className="line-chart">
      <div className="line-chart-head">
        <span className="muted">max {format(maximum)}</span>
        {shown && (
          <span className="line-chart-value">
            {new Date(shown.start).toLocaleTimeString()} · <strong>{shown.value === null ? 'no data' : format(shown.value)}</strong>
          </span>
        )}
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" className="line-chart-svg" role="img"
        aria-label="Metric over time">
        {segments.map((segment, index) => (
          <g key={index}>
            <path
              className="line-area"
              d={`M${segment[0][0]},${HEIGHT} ${segment.map(([px, py]) => `L${px},${py}`).join(' ')} L${segment[segment.length - 1][0]},${HEIGHT} Z`}
            />
            <path className="line-path" d={`M${segment.map(([px, py]) => `${px},${py}`).join(' L')}`} />
          </g>
        ))}
        {points.map((point, index) => (
          <rect
            key={point.start}
            x={x(index) - step / 2}
            y="0"
            width={step}
            height={HEIGHT}
            className={`line-hit ${hovered === index ? 'is-hovered' : ''}`}
            onMouseEnter={() => setHovered(index)}
            onMouseLeave={() => setHovered(null)}
          />
        ))}
      </svg>
    </div>
  )
}

export default LineChart

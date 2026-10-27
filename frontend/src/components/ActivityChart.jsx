import { useState } from 'react'

// Rounds the top of the chart up to a clean number such as 50, 100 or 2,000
function niceMaximum(value) {
  if (value <= 4) return 4
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find((multiple) => multiple * power >= value)
  return step * power
}

function compact(value) {
  return value >= 1000 ? `${value / 1000}K` : String(value)
}

function formatSlot(date, wholeRangeMs) {
  const options =
    wholeRangeMs > 2 * 24 * 3600 * 1000
      ? { month: 'short', day: 'numeric' }
      : { hour: '2-digit', minute: '2-digit', ...(wholeRangeMs < 15 * 60 * 1000 && { second: '2-digit' }) }
  return date.toLocaleString([], options)
}

// Stacked columns over time: errors (red), warnings (amber) and everything else (grey).
// Hovering a column shows its exact numbers.
function ActivityChart({ slots }) {
  const [hovered, setHovered] = useState(null)

  if (slots.length === 0) return <p className="empty">No activity yet.</p>

  const maximum = niceMaximum(Math.max(...slots.map((slot) => slot.total)))
  const first = new Date(slots[0].start)
  const last = new Date(slots[slots.length - 1].start)
  const rangeMs = last - first
  const ticks = [maximum, maximum / 2, 0]

  return (
    <div className="activity">
      <ul className="legend-row">
        <li><span className="swatch fill-error" />Errors</li>
        <li><span className="swatch fill-warning" />Warnings</li>
        <li><span className="swatch fill-other" />Other logs</li>
      </ul>

      <div className="plot">
        <div className="y-axis">
          {ticks.map((tick) => (
            <span key={tick} style={{ bottom: `${(tick / maximum) * 100}%` }}>
              {compact(tick)}
            </span>
          ))}
        </div>
        <div className="plot-area">
          {ticks.map((tick) => (
            <span key={tick} className="gridline" style={{ bottom: `${(tick / maximum) * 100}%` }} />
          ))}
          <div className="columns">
            {slots.map((slot, index) => {
              const other = slot.total - slot.errors - slot.warnings
              return (
                <div
                  key={index}
                  className="column-hit"
                  onMouseEnter={() => setHovered(index)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <div
                    className={`column ${hovered === index ? 'is-hovered' : ''}`}
                    style={{ height: `${(slot.total / maximum) * 100}%`, '--i': index }}
                  >
                    {other > 0 && <span className="fill-other" style={{ flexGrow: other }} />}
                    {slot.warnings > 0 && <span className="fill-warning" style={{ flexGrow: slot.warnings }} />}
                    {slot.errors > 0 && <span className="fill-error" style={{ flexGrow: slot.errors }} />}
                  </div>
                  {hovered === index && (
                    <div className={`tooltip ${index > slots.length / 2 ? 'to-left' : ''}`}>
                      <p className="tooltip-title">{formatSlot(new Date(slot.start), rangeMs || 60000)}</p>
                      <p><span className="swatch fill-error" />Errors <strong>{slot.errors}</strong></p>
                      <p><span className="swatch fill-warning" />Warnings <strong>{slot.warnings}</strong></p>
                      <p><span className="swatch fill-other" />Other <strong>{other}</strong></p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="x-axis">
        <span>{formatSlot(first, rangeMs)}</span>
        <span>{formatSlot(new Date(slots[Math.floor(slots.length / 2)].start), rangeMs)}</span>
        <span>{formatSlot(last, rangeMs)}</span>
      </div>
    </div>
  )
}

export default ActivityChart

// A ranked list with a bar for each item, such as "most common error types".
// Each item: { label, value, part } - "part" (optional) is the red share of the bar.
function BarList({ items, emptyText }) {
  if (items.length === 0) return <p className="empty">{emptyText}</p>
  const largest = items[0].value

  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li key={item.label}>
          <span className="bar-label" title={item.label}>
            {item.label}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(item.value / largest) * 100}%` }}>
              {item.part > 0 && (
                <span className="bar-part" style={{ width: `${(item.part / item.value) * 100}%` }} />
              )}
            </span>
          </span>
          <strong>{item.value.toLocaleString()}</strong>
        </li>
      ))}
    </ul>
  )
}

export default BarList

// Small helpers for showing times in a friendly way.

// "8 Oct, 10:15" (the year is added when it is not this year)
export function formatMoment(value) {
  if (!value) return '-'
  const date = new Date(value)
  return date.toLocaleString([], {
    ...(date.getFullYear() !== new Date().getFullYear() && { year: 'numeric' }),
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// "45 s", "12 min", "3 h 20 min" or "2 days"
export function formatDuration(start, end) {
  if (!start || !end) return '-'
  const seconds = Math.max(0, (new Date(end) - new Date(start)) / 1000)
  if (seconds < 60) return `${Math.round(seconds)} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.round((seconds % 3600) / 60)
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`
  }
  return `${Math.round(seconds / 86400)} days`
}

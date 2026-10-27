import AnimatedNumber from './AnimatedNumber.jsx'

// One headline number on the dashboard, with a label and a short note.
function StatCard({ label, value, note, tone = 'neutral' }) {
  return (
    <div className={`glass card stat-card tone-${tone}`}>
      <p className="eyebrow">{label}</p>
      <p className="stat-value">
        {typeof value === 'number' ? <AnimatedNumber value={value} /> : value}
      </p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  )
}

export default StatCard

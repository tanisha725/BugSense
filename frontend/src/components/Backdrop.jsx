// The soft coloured light behind every page. It is decoration only,
// so it is hidden from screen readers and cannot be clicked.
function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <span className="glow glow-one" />
      <span className="glow glow-two" />
      <span className="glow glow-three" />
    </div>
  )
}

export default Backdrop

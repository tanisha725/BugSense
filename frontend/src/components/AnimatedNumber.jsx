import { useEffect, useRef, useState } from 'react'

// Shows a number that counts up smoothly to its new value.
function AnimatedNumber({ value, duration = 700 }) {
  const [shown, setShown] = useState(value)
  const previous = useRef(value)

  useEffect(() => {
    const from = previous.current
    previous.current = value
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (from === value || reduceMotion) {
      setShown(value)
      return
    }
    const startTime = performance.now()
    let frame
    function step(now) {
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - (1 - progress) ** 3 // fast at first, slow at the end
      setShown(Math.round(from + (value - from) * eased))
      if (progress < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [value, duration])

  return shown.toLocaleString()
}

export default AnimatedNumber

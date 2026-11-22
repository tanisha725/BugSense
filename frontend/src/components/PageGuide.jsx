import { useState } from 'react'
import { GUIDES } from './guides.js'

function remembered(page) {
  try {
    return localStorage.getItem(`bugsense.guide.${page}`) !== 'closed'
  } catch {
    return true
  }
}

// A short, plain-language explanation at the top of a page: what it is for,
// how to use it in three steps, and the words it uses. It can be folded away,
// and the browser remembers that.
function PageGuide({ page }) {
  const guide = GUIDES[page]
  const [open, setOpen] = useState(() => remembered(page))
  if (!guide) return null

  function toggle() {
    setOpen(!open)
    try {
      localStorage.setItem(`bugsense.guide.${page}`, open ? 'closed' : 'open')
    } catch {
      // Storage can be blocked; the guide still folds for this visit
    }
  }

  return (
    <section className={`page-guide ${open ? 'open' : ''}`}>
      <button type="button" className="page-guide-toggle" onClick={toggle} aria-expanded={open}>
        <span className="page-guide-icon" aria-hidden="true">?</span>
        <span>
          <strong>In simple words:</strong> {guide.what}
        </span>
        <span className="page-guide-chevron" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="page-guide-body">
          <div>
            <p className="page-guide-label">How to use it</p>
            <ol>
              {guide.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
          {guide.words && (
            <div>
              <p className="page-guide-label">Words on this page</p>
              <dl>
                {guide.words.map(([word, meaning]) => (
                  <div key={word}>
                    <dt>{word}</dt>
                    <dd>{meaning}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {guide.why && <p className="page-guide-why"><strong>Why it helps:</strong> {guide.why}</p>}
        </div>
      )}
    </section>
  )
}

export default PageGuide

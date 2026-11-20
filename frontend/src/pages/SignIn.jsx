import { useEffect, useState } from 'react'
import { getAuthStatus, signIn, signUp } from '../services/api.js'

// The page shown to anyone who is not signed in. The very first visit creates
// the owner account; after that, new accounts are only possible if the owner
// switched sign-up on (ALLOW_SIGNUP=true on the server).
function SignIn({ onSignedIn }) {
  const [status, setStatus] = useState(null)
  const [mode, setMode] = useState('signin')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getAuthStatus()
      .then((result) => {
        setStatus(result)
        if (!result.has_users) setMode('signup')
      })
      .catch(() => setError('Cannot reach the BugSense server. Is the backend running?'))
  }, [])

  function update(name, value) {
    setForm({ ...form, [name]: value })
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result =
        mode === 'signup'
          ? await signUp(form.name, form.email, form.password)
          : await signIn(form.email, form.password)
      onSignedIn(result.token, result.user)
    } catch (problem) {
      setError(problem.message)
    } finally {
      setBusy(false)
    }
  }

  const firstAccount = status && !status.has_users

  return (
    <main className="signin-page">
      <section className="glass card signin-card">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="10" fill="#111113" />
            <path d="M6 17h5l2.5-7 4 13 2.5-6h6" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <p className="brand-name">BugSense</p>
            <p className="brand-tagline">Incident analysis</p>
          </div>
        </div>

        <h1 className="signin-title">{mode === 'signup' ? (firstAccount ? 'Create the owner account' : 'Create an account') : 'Sign in'}</h1>
        {firstAccount && (
          <p className="muted">This is the first visit. The account you create now owns this BugSense.</p>
        )}

        <form onSubmit={submit} className="signin-form">
          {mode === 'signup' && (
            <label className="field">
              <span>Name</span>
              <input className="input" autoComplete="name" required value={form.name} onChange={(event) => update('name', event.target.value)} />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input className="input" type="email" autoComplete="email" required value={form.email} onChange={(event) => update('email', event.target.value)} />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              className="input"
              type="password"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              minLength={mode === 'signup' ? 8 : undefined}
              required
              value={form.password}
              onChange={(event) => update('password', event.target.value)}
            />
          </label>
          {mode === 'signup' && <p className="muted small">At least 8 characters.</p>}
          {error && <p className="notice bad">{error}</p>}
          <button className="button" disabled={busy || !status}>
            {busy ? 'Please wait...' : mode === 'signup' ? 'Create account' : 'Sign in'}
          </button>
        </form>

        {status?.has_users && status.signup_open && (
          <button type="button" className="link-button" onClick={() => setMode(mode === 'signup' ? 'signin' : 'signup')}>
            {mode === 'signup' ? 'I already have an account' : 'Create an account'}
          </button>
        )}
        {status?.has_users && !status.signup_open && mode === 'signin' && (
          <p className="muted small">New accounts are created by the owner.</p>
        )}
      </section>
    </main>
  )
}

export default SignIn

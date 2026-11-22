import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Backdrop from './components/Backdrop.jsx'
import TopNav from './components/TopNav.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DatasetDetail from './pages/DatasetDetail.jsx'
import Datasets from './pages/Datasets.jsx'
import IncidentDetail from './pages/IncidentDetail.jsx'
import Incidents from './pages/Incidents.jsx'
import Logs from './pages/Logs.jsx'
import Services from './pages/Services.jsx'
import SignIn from './pages/SignIn.jsx'
import Telemetry from './pages/Telemetry.jsx'
import Tools from './pages/Tools.jsx'
import Value from './pages/Value.jsx'
import {
  SIGNED_OUT_EVENT,
  getHealth,
  getIncidentSummary,
  getMe,
  getProjects,
  getServedBy,
  getStreamStatus,
  getToken,
  setToken,
} from './services/api.js'

// The chosen project is remembered in the browser between visits
function savedProjectId() {
  try {
    return Number(localStorage.getItem('bugsense.project')) || null
  } catch {
    return null
  }
}

// Everything after signing in
function Workspace({ user, onSignOut }) {
  const [health, setHealth] = useState(null) // null while checking
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(savedProjectId)
  const [stream, setStream] = useState(null) // the live replay status
  const [criticalIncidents, setCriticalIncidents] = useState(0)
  const [servedBy, setServedBy] = useState(null) // web-main or web-backup, on Podman

  const loadProjects = useCallback(() => {
    getProjects().then(setProjects).catch(() => setProjects([]))
  }, [])

  // Runs once when the app loads
  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ backend: 'online', database: data.database }))
      .catch(() => setHealth({ backend: 'offline', database: null }))
    loadProjects()
  }, [loadProjects])

  // Every 3 seconds: is a live stream running, and are there critical incidents?
  // (asking again and again like this is called "polling")
  useEffect(() => {
    function check() {
      getStreamStatus().then(setStream).catch(() => setStream(null))
      getIncidentSummary()
        .then((summary) => setCriticalIncidents(summary.critical))
        .catch(() => setCriticalIncidents(0))
      getServedBy().then(setServedBy)
    }
    check()
    const timer = setInterval(check, 3000)
    return () => clearInterval(timer)
  }, [])

  function chooseProject(id) {
    setProjectId(id)
    try {
      localStorage.setItem('bugsense.project', id ?? '')
    } catch {
      // Storage can be blocked (for example in private mode). The choice still works.
    }
  }

  // A stream counts as "live here" when it writes into the project being viewed
  const live = Boolean(stream?.running && (projectId === null || projectId === stream.project_id))
  const project = projects.find((item) => item.id === projectId) || null

  return (
    <BrowserRouter>
      <Backdrop />
      <div className="app">
        <TopNav
          health={health}
          projects={projects}
          projectId={projectId}
          onProjectChange={chooseProject}
          stream={stream}
          criticalIncidents={criticalIncidents}
          user={user}
          onSignOut={onSignOut}
          servedBy={servedBy}
        />
        <main className="content">
          <Routes>
            <Route
              path="/"
              element={<Dashboard health={health} project={project} projectId={projectId} live={live} />}
            />
            <Route
              path="/incidents"
              element={<Incidents project={project} projectId={projectId} live={live} />}
            />
            <Route path="/incidents/:id" element={<IncidentDetail live={live} />} />
            <Route
              path="/services"
              element={
                <Services
                  onProjectChange={(id) => {
                    loadProjects()
                    chooseProject(id)
                  }}
                />
              }
            />
            <Route path="/telemetry" element={<Telemetry project={project} projectId={projectId} />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/value" element={<Value />} />
            <Route
              path="/logs"
              element={<Logs project={project} projectId={projectId} live={live} onChange={loadProjects} />}
            />
            <Route
              path="/datasets/:key"
              element={
                <DatasetDetail
                  onStreamChange={setStream}
                  onProjectChange={(id) => {
                    loadProjects()
                    chooseProject(id)
                  }}
                />
              }
            />
            <Route
              path="/datasets"
              element={
                <Datasets
                  stream={stream}
                  onStreamChange={setStream}
                  onProjectChange={(id) => {
                    loadProjects()
                    chooseProject(id)
                  }}
                />
              }
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

// Shows the sign-in page until the user is signed in, then the workspace
function App() {
  // undefined while checking a saved token, null when signed out
  const [user, setUser] = useState(getToken() ? undefined : null)

  useEffect(() => {
    if (!getToken()) return
    getMe()
      .then(setUser)
      .catch(() => {
        setToken(null)
        setUser(null)
      })
  }, [])

  // Any request that comes back "please sign in" (expired token) signs out
  useEffect(() => {
    const signedOut = () => setUser(null)
    window.addEventListener(SIGNED_OUT_EVENT, signedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, signedOut)
  }, [])

  function handleSignedIn(token, signedInUser) {
    setToken(token)
    setUser(signedInUser)
  }

  function handleSignOut() {
    setToken(null)
    setUser(null)
  }

  if (user === undefined) return <p className="empty">Loading...</p>
  if (user === null) {
    return (
      <>
        <Backdrop />
        <SignIn onSignedIn={handleSignedIn} />
      </>
    )
  }
  return <Workspace user={user} onSignOut={handleSignOut} />
}

export default App

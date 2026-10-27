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
import { getHealth, getIncidentSummary, getProjects, getStreamStatus } from './services/api.js'

// The chosen project is remembered in the browser between visits
function savedProjectId() {
  try {
    return Number(localStorage.getItem('bugsense.project')) || null
  } catch {
    return null
  }
}

function App() {
  const [health, setHealth] = useState(null) // null while checking
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(savedProjectId)
  const [stream, setStream] = useState(null) // the live replay status
  const [criticalIncidents, setCriticalIncidents] = useState(0)

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

export default App

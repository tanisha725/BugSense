// The plain-language guide shown at the top of each page (see PageGuide.jsx).
export const GUIDES = {
  overview: {
    what: 'The health of everything at a glance: how many logs, how many problems, and how bad they are.',
    steps: [
      'Pick a project in the top bar (or keep "All projects").',
      'Look at the numbers: errors and critical incidents are the ones to worry about.',
      'Click through to Incidents to see what went wrong.',
    ],
    words: [
      ['Log', 'One line a program writes about what it is doing, for example "payment failed".'],
      ['Incident', 'A group of errors that happened close together, treated as one problem.'],
      ['Severity', 'How bad a log or incident is: info, warning, error, critical.'],
    ],
    why: 'An engineer sees in five seconds whether anything needs attention, instead of opening many dashboards.',
  },
  incidents: {
    what: 'BugSense groups errors that happen close together into incidents, so 500 error lines become one problem to solve.',
    steps: [
      'Incidents are found by themselves when logs arrive ("Run detection again" redoes it).',
      'Filter by status, severity or service to find the one you care about.',
      'Open an incident to see where it started and to ask for a diagnosis.',
    ],
    words: [
      ['Root cause', 'The service where the problem really started; the others only suffered from it.'],
      ['Diagnosis', 'BugSense\'s explanation of the probable cause, with the evidence it used.'],
      ['Open / resolved', 'Whether someone still has to deal with it.'],
    ],
    why: 'Engineers stop reading thousands of lines one by one; they start from one incident with a ranked list of suspects.',
  },
  incident: {
    what: 'One problem, explained: which service started it, how it spread, and the probable cause with its evidence.',
    steps: [
      'Read "Where did it start?": services ranked from the probable origin to the ones only affected.',
      'Press "Find probable cause". "Rules" is free and instant; "AI" reads more and explains more; "Auto" picks for you.',
      'Check the evidence list, then mark the incident resolved when it is fixed.',
    ],
    words: [
      ['Confidence', 'How sure BugSense is: high, medium or low, with the reason.'],
      ['Evidence', 'The facts behind the answer, and which tool found each one.'],
      ['Tokens', 'How much text the AI read; this is what an AI provider charges for.'],
    ],
    why: 'The first hypothesis arrives in seconds, with proof, so the engineer checks it instead of searching from zero.',
  },
  services: {
    what: 'A small online shop (shop-web, shop-api, shop-db) that BugSense watches live. You can break it on purpose to see BugSense find the problem.',
    steps: [
      'Press "Start all": the three programs start and send live data.',
      'Stop shop-db, or restart shop-api with a fault (crash, slow, bad config).',
      'Watch Telemetry turn red, then open the new incident and press "Find probable cause".',
    ],
    words: [
      ['Service', 'One running program, for example the shop\'s database.'],
      ['Restart / crash', 'A service stopped; BugSense notes whether it was planned or an accident.'],
      ['Fault', 'A problem you switch on for the demo, so the cause is known in advance.'],
    ],
    why: 'It proves BugSense works on a live system with a known cause, which makes the demo convincing.',
  },
  telemetry: {
    what: 'The health of each service: how many requests, how many failed, how fast they answered. It comes live from running programs, or BugSense calculates it from logs you upload.',
    steps: [
      'Pick a project in the top bar. Uploaded logs open on "All data" by themselves, because their times are in the past.',
      'Each card is one service. Green means healthy; red means at least 1 in 5 requests (or log lines) is failing.',
      'Click a trace (one customer request) to see every service it passed through, and which one failed.',
    ],
    words: [
      ['Telemetry', 'Data programs send about themselves while they run, like a car\'s dashboard.'],
      ['Trace', 'The journey of one request: web → api → db, with the time each step took.'],
      ['Metric', 'A number measured over time, such as requests per minute or memory.'],
      ['p95 latency', '95 of every 100 requests were answered faster than this. It shows what slow customers feel.'],
      ['OpenTelemetry', 'The open standard for sending telemetry. Huawei Cloud AOM and APM accept it too.'],
    ],
    why: 'Problems show up the moment they start, and a trace points to the exact failing hop, without reading logs.',
  },
  logs: {
    what: 'Every log line BugSense has received, in one place, with search and filters.',
    steps: [
      'Upload a log file, or paste lines, or let the live shop send them.',
      'Filter by severity, service, error type, request ID or time.',
      'Export what you found as CSV to share it.',
    ],
    words: [
      ['Request ID', 'A label that follows one customer request across services, so its lines can be joined.'],
      ['Error type', 'The kind of error BugSense recognised, for example timeout or connection refused.'],
    ],
    why: 'One search across all services replaces logging into each server separately.',
  },
  datasets: {
    what: 'Real logs from real systems (Hadoop, OpenStack, ZooKeeper and more), ready to import, so BugSense can be tested on data it has never seen.',
    steps: [
      'Pick a dataset and press Import (all at once) or Stream live (line by line, as if it were happening now).',
      'Go to Incidents and Telemetry to see what BugSense found in it.',
      'Compare with the known answer on the dataset page.',
    ],
    why: 'It shows BugSense on real company-scale logs, not only on our own demo.',
  },
  tools: {
    what: 'The 10 investigation tools BugSense uses to diagnose a problem. The AI picks them itself; here you can try each one by hand.',
    steps: [
      'Pick a tool on the left. Each one answers one question (shown under its name).',
      'Fill in only what you need; empty fields use sensible defaults.',
      'Press "Run tool" and read the answer. A wrong value is refused with a clear message.',
    ],
    words: [
      ['Tool', 'A small, read-only question BugSense can ask its data, like "which service failed first?".'],
      ['Parameter', 'A setting for the question, for example which service or how many results.'],
      ['Schema', 'The exact list of parameters and allowed values that the AI is shown.'],
    ],
    why: 'The AI can only use these read-only tools, so it can never change anything in production, and every step it took can be repeated.',
  },
}

import { useEffect, useState } from 'react'
import { getAiConfig, getTools, runTool } from '../services/api.js'

// The JSON Schema of one parameter, without the "or null" part of optional ones
function fieldType(field) {
  const options = field.anyOf ? field.anyOf.filter((option) => option.type !== 'null') : [field]
  return { ...field, ...options[0] }
}

// One form field, chosen from the parameter's schema
function ParameterInput({ name, field, required, value, onChange }) {
  const type = fieldType(field)
  const id = `param-${name}`

  let input
  if (type.enum) {
    input = (
      <select id={id} className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        {!required && <option value="">(not set{field.default !== undefined && field.default !== null ? `, default ${field.default}` : ''})</option>}
        {type.enum.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    )
  } else if (type.type === 'boolean') {
    input = (
      <select id={id} className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">(default {String(field.default)})</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    )
  } else if (type.type === 'integer' || type.type === 'number') {
    input = (
      <input
        id={id}
        className="input"
        type="number"
        min={type.minimum}
        max={type.maximum}
        step={type.type === 'integer' ? 1 : 'any'}
        placeholder={field.default !== undefined && field.default !== null ? `default ${field.default}` : ''}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    )
  } else if (type.format === 'date-time') {
    input = <input id={id} className="input" type="datetime-local" step="1" value={value} onChange={(event) => onChange(event.target.value)} />
  } else {
    input = <input id={id} className="input" placeholder={type.pattern ? `format ${type.pattern}` : ''} value={value} onChange={(event) => onChange(event.target.value)} />
  }

  const limits = [
    type.minimum !== undefined && `min ${type.minimum}`,
    type.maximum !== undefined && `max ${type.maximum}`,
    type.maxLength !== undefined && `up to ${type.maxLength} characters`,
  ].filter(Boolean)

  return (
    <div className="tool-field">
      <label htmlFor={id}>
        <span className="mono">{name}</span>
        {required && <span className="required">required</span>}
        <span className="tool-type">{type.format || type.type || 'value'}</span>
      </label>
      {input}
      <p className="tool-help">
        {field.description}
        {limits.length > 0 && <span className="muted"> ({limits.join(', ')})</span>}
      </p>
    </div>
  )
}

// Turns the form's text values into typed parameters, leaving out empty ones
function toParameters(schema, values) {
  const parameters = {}
  for (const [name, field] of Object.entries(schema.properties)) {
    const value = values[name]
    if (value === undefined || value === '') continue
    const type = fieldType(field)
    if (type.type === 'integer' || type.type === 'number') parameters[name] = Number(value)
    else if (type.type === 'boolean') parameters[name] = value === 'true'
    else parameters[name] = value
  }
  return parameters
}

// Every investigation tool, with a form for its parameters. The AI uses the
// same tools with the same parameters, so this page shows exactly what it can do.
function Tools() {
  const [tools, setTools] = useState([])
  const [config, setConfig] = useState(null)
  const [selected, setSelected] = useState(null)
  const [values, setValues] = useState({})
  const [output, setOutput] = useState(null)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)
  const [showSchema, setShowSchema] = useState(false)

  useEffect(() => {
    getTools()
      .then((list) => {
        setTools(list)
        setSelected(list[0]?.name ?? null)
      })
      .catch((problem) => setError(problem.message))
    getAiConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const tool = tools.find((item) => item.name === selected)

  function choose(name) {
    setSelected(name)
    setValues({})
    setOutput(null)
    setError(null)
  }

  async function handleRun(event) {
    event.preventDefault()
    setRunning(true)
    setError(null)
    try {
      setOutput(await runTool(tool.name, toParameters(tool.parameters, values)))
    } catch (problem) {
      setOutput(null)
      setError(problem.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Tools</h1>
        <p>
          The {tools.length} investigation tools BugSense uses to diagnose incidents. The AI chooses them itself; here
          you can run any of them by hand. Every parameter is checked: a wrong value is refused, never ignored.
        </p>
        {config && (
          <p className="muted">
            AI model: <strong>{config.model}</strong> via {config.provider} ·{' '}
            {config.llm_available ? 'key set, AI diagnosis available' : 'no key set, the rule-based investigator is used'}
          </p>
        )}
      </header>

      <div className="tools-layout">
        <nav className="glass card tool-list" aria-label="Tools">
          {tools.map((item) => (
            <button
              key={item.name}
              type="button"
              className={`tool-item ${item.name === selected ? 'active' : ''}`}
              onClick={() => choose(item.name)}
            >
              <span className="mono">{item.name}</span>
              <span className="tool-count">{Object.keys(item.parameters.properties).length} parameters</span>
            </button>
          ))}
        </nav>

        {tool && (
          <section className="glass card">
            <div className="card-header">
              <div>
                <h3 className="mono">{tool.name}</h3>
                <p className="muted">{tool.description}</p>
              </div>
              <button type="button" className="button button-quiet button-small" onClick={() => setShowSchema(!showSchema)}>
                {showSchema ? 'Hide schema' : 'Schema the AI sees'}
              </button>
            </div>
            {showSchema && <pre className="json-view">{JSON.stringify(tool.parameters, null, 2)}</pre>}

            <form onSubmit={handleRun}>
              <div className="tool-fields">
                {Object.entries(tool.parameters.properties).map(([name, field]) => (
                  <ParameterInput
                    key={name}
                    name={name}
                    field={field}
                    required={tool.parameters.required?.includes(name)}
                    value={values[name] ?? ''}
                    onChange={(value) => setValues({ ...values, [name]: value })}
                  />
                ))}
              </div>
              <div className="form-footer">
                <span className="muted">Empty fields use their default.</span>
                <button className="button" disabled={running}>
                  {running ? 'Running...' : 'Run tool'}
                </button>
              </div>
            </form>

            {error && <p className="notice bad">{error}</p>}
            {output && (
              <div className="tool-output">
                <p className="muted">
                  Ran in {output.duration_ms} ms with <code>{JSON.stringify(output.parameters)}</code>
                </p>
                <pre className="json-view">{JSON.stringify(output.result, null, 2)}</pre>
              </div>
            )}
          </section>
        )}
      </div>
    </>
  )
}

export default Tools

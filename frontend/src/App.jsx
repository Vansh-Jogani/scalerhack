import { useState, useEffect, useRef } from 'react'
import Map from './Map'

const SCENARIO_CENTER = { lat: 34.0580, lon: -118.2400 }
const INCIDENT_RADIUS_M = 600

const STATUS_COLOR = {
  STANDBY: '#888',
  SURVEILLANCE_ACTIVE: '#00aaff',
  SWARM_ACTIVE: '#ffaa00',
  ADVISORY_ACTIVE: '#00ffaa',
}

const AGENT_COLORS = {
  agent1: '#00aaff',
  agent2: '#ffaa00',
  agent3: '#00ffaa',
  system: '#666',
}

function App() {
  const [droneData, setDroneData] = useState({})
  const [markers, setMarkers] = useState([])
  const [zones, setZones] = useState([])
  const [survivors, setSurvivors] = useState([])
  const [state, setState] = useState('STANDBY')
  const [advisory, setAdvisory] = useState(null)
  const [incident, setIncident] = useState(null)
  const [agentLogs, setAgentLogs] = useState([])
  const ws = useRef(null)

  const addLog = (entry) =>
    setAgentLogs((prev) => [entry, ...prev].slice(0, 40))

  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket(`ws://localhost:8000/ws`)
      ws.current.onopen = () =>
        addLog({ agent: 'system', msg: 'Connected to ARIA backend', ts: Date.now() })
      ws.current.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'telemetry') {
          setDroneData((prev) => ({ ...prev, [msg.data.drone_id]: msg.data }))
        } else if (msg.type === 'markers') {
          setMarkers(msg.data)
        } else if (msg.type === 'zones') {
          setZones(msg.data)
        } else if (msg.type === 'survivors') {
          setSurvivors(msg.data)
        } else if (msg.type === 'advisory') {
          setAdvisory(msg.data)
          setState('ADVISORY_ACTIVE')
          addLog({ agent: 'agent3', msg: 'Advisory issued', ts: Date.now() })
        } else if (msg.type === 'incident') {
          setIncident(msg.data)
          addLog({ agent: 'system', msg: `Incident confirmed: ${msg.data.classification} (${(msg.data.confidence * 100).toFixed(0)}%)`, ts: Date.now() })
        } else if (msg.type === 'agent_log') {
          addLog({ agent: msg.agent, msg: msg.msg, ts: Date.now() })
        } else if (msg.type === 'ack') {
          if (msg.action === 'go') {
            setState('SURVEILLANCE_ACTIVE')
            addLog({ agent: 'system', msg: `GO acknowledged — incident ${msg.incident_id}`, ts: Date.now() })
          }
        }
      }
      ws.current.onclose = () => {
        addLog({ agent: 'system', msg: 'Disconnected — retrying...', ts: Date.now() })
        setTimeout(connect, 2000)
      }
    }
    connect()
    return () => ws.current?.close()
  }, [])

  const sendGo = () => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return
    ws.current.send(JSON.stringify({
      type: 'command',
      action: 'go',
      data: {
        area: {
          center: SCENARIO_CENTER,
          radius_m: INCIDENT_RADIUS_M,
        },
        disaster_type: 'fire',
      },
    }))
    addLog({ agent: 'system', msg: 'GO signal sent — fire scenario', ts: Date.now() })
  }

  const stateColor = STATUS_COLOR[state] || '#888'
  const droneCount = Object.keys(droneData).length

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', background: '#0d0d0d', fontFamily: 'monospace' }}>
      {/* Map */}
      <div style={{ flex: 1, position: 'relative' }}>
        <Map drones={droneData} markers={markers} zones={zones} survivors={survivors} incident={incident} />

        {/* Top bar */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0,
          background: 'rgba(0,0,0,0.82)', padding: '10px 16px',
          display: 'flex', alignItems: 'center', gap: 16, zIndex: 1000,
          borderBottom: '1px solid #222',
        }}>
          <span style={{ color: '#00ffaa', fontWeight: 'bold', fontSize: 15, letterSpacing: 2 }}>ARIA v1</span>
          <span style={{ color: stateColor, fontSize: 12, border: `1px solid ${stateColor}`, padding: '2px 8px', borderRadius: 3 }}>
            {state}
          </span>
          <span style={{ color: '#555', fontSize: 11 }}>DRONES: <span style={{ color: '#ccc' }}>{droneCount}</span></span>
          <span style={{ color: '#555', fontSize: 11 }}>MARKERS: <span style={{ color: '#ccc' }}>{markers.length}</span></span>
          {incident && (
            <span style={{ color: '#ffaa00', fontSize: 11, border: '1px solid #ffaa00', padding: '2px 8px', borderRadius: 3 }}>
              {incident.classification.toUpperCase()} {(incident.confidence * 100).toFixed(0)}%
            </span>
          )}
          <div style={{ flex: 1 }} />
          <button
            onClick={sendGo}
            disabled={state !== 'STANDBY'}
            style={{
              background: state === 'STANDBY' ? '#cc2200' : '#333',
              color: state === 'STANDBY' ? '#fff' : '#666',
              border: 'none', padding: '6px 20px', borderRadius: 3,
              fontFamily: 'monospace', fontWeight: 'bold', fontSize: 13,
              cursor: state === 'STANDBY' ? 'pointer' : 'default',
              letterSpacing: 1,
            }}
          >
            GO
          </button>
        </div>
      </div>

      {/* Sidebar */}
      <div style={{
        width: 300, background: '#0a0a0a', borderLeft: '1px solid #1e1e1e',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Advisory */}
        <div style={{ padding: 12, borderBottom: '1px solid #1e1e1e', maxHeight: 220, overflowY: 'auto' }}>
          <div style={{ color: '#444', fontSize: 10, marginBottom: 6, letterSpacing: 1 }}>ADVISORY</div>
          {advisory ? (
            <div style={{ fontSize: 11, color: '#ccc' }}>
              <div style={{ color: '#00ffaa', marginBottom: 6, lineHeight: 1.5 }}>{advisory.situation_summary}</div>
              {advisory.immediate_actions?.map((a, i) => (
                <div key={i} style={{ color: '#aaa', marginBottom: 2, paddingLeft: 8, borderLeft: '2px solid #333' }}>
                  {a}
                </div>
              ))}
              {advisory.risk_flags?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ color: '#ff6644', fontSize: 10, marginBottom: 3, letterSpacing: 1 }}>RISK FLAGS</div>
                  {advisory.risk_flags.map((f, i) => (
                    <div key={i} style={{ color: '#ff9977', fontSize: 10, marginBottom: 2 }}>⚠ {f}</div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: '#2a2a2a', fontSize: 11 }}>Awaiting Agent 3…</div>
          )}
        </div>

        {/* Drone status */}
        <div style={{ padding: 12, borderBottom: '1px solid #1e1e1e' }}>
          <div style={{ color: '#444', fontSize: 10, marginBottom: 6, letterSpacing: 1 }}>DRONE STATUS</div>
          {droneCount === 0 ? (
            <div style={{ color: '#222', fontSize: 11 }}>No drones active</div>
          ) : Object.entries(droneData).map(([id, d]) => (
            <div key={id} style={{ marginBottom: 4, fontSize: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ color: id.startsWith('swarm') ? '#ffaa00' : '#00aaff', minWidth: 80 }}>{id}</span>
              <span style={{ color: '#333' }}>{d.state}</span>
              <span style={{ color: '#444', marginLeft: 'auto' }}>{d.battery_pct?.toFixed(0)}%</span>
            </div>
          ))}
        </div>

        {/* Agent stream log */}
        <div style={{ padding: 12, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ color: '#444', fontSize: 10, marginBottom: 6, letterSpacing: 1 }}>AGENT STREAM</div>
          <div style={{ overflow: 'auto', flex: 1 }}>
            {agentLogs.map((entry, i) => {
              const color = AGENT_COLORS[entry.agent] || '#555'
              const label = entry.agent === 'system' ? 'SYS' :
                            entry.agent === 'agent1' ? 'A1' :
                            entry.agent === 'agent2' ? 'A2' : 'A3'
              return (
                <div key={i} style={{ marginBottom: 4, lineHeight: 1.4 }}>
                  <span style={{ color, fontSize: 9, fontWeight: 'bold', marginRight: 5 }}>[{label}]</span>
                  <span style={{ color: '#555', fontSize: 10 }}>{entry.msg}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App

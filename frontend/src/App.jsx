import { useState, useEffect, useRef, useCallback } from 'react'
import Map from './Map'
import SidePanel from './SidePanel'
import MapStateManager from './MapStateManager'

function useReconnectingWS(path, onMessage) {
  const cbRef = useRef(onMessage)
  cbRef.current = onMessage
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws, stopped = false
    function connect() {
      ws = new WebSocket(`ws://${window.location.host}${path}`)
      wsRef.current = ws
      ws.onmessage = (e) => { try { cbRef.current(JSON.parse(e.data)) } catch {} }
      ws.onclose = () => { wsRef.current = null; if (!stopped) setTimeout(connect, 2000) }
    }
    connect()
    return () => { stopped = true; wsRef.current?.close() }
  }, [path])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
      return true
    }
    return false
  }, [])

  return { connected, send }
}

export default function App() {
  const [incidents, setIncidents] = useState({})
  const [isSelectingLocation, setIsSelectingLocation] = useState(false)
  const [capturedCoords, setCapturedCoords] = useState(null)
  const [advisory, setAdvisory] = useState(null)
  const [agentStates, setAgentStates] = useState({ A1: 'idle', A2: 'idle', A3: 'idle' })
  const [feedEntries, setFeedEntries] = useState([])
  const [wsConnected, setWsConnected] = useState(false)

  const systemStatus = Object.values(incidents).some(i => i.status === 'EMERGENCY')
    ? 'EMERGENCY' : Object.values(incidents).length > 0 ? 'ACTIVE' : 'NOMINAL'

  const addFeedEntry = useCallback((entry) => {
    setFeedEntries(prev => [entry, ...prev].slice(0, 200))
  }, [])

  useReconnectingWS('/ws', useCallback((msg) => {
    if (msg.type === 'hello') {
      setWsConnected(true)
      if (msg.bases) MapStateManager.renderBases(msg.bases)
    }
    if (msg.type === 'bases' && Array.isArray(msg.data)) MapStateManager.renderBases(msg.data)

    if (msg.type === 'telemetry') {
      MapStateManager.receive({ type: 'map_update', action: 'update_drone', incident_id: null, payload: msg.data })
    }
    if (msg.type === 'markers') {
      msg.data?.forEach((m) => {
        MapStateManager.receive({ type: 'map_update', action: 'add_marker', incident_id: m.id,
          payload: { lat: m.lat, lon: m.lon, type: m.type, severity: m.severity || 'MEDIUM', status: 'ACTIVE' } })
        setIncidents(prev => ({ ...prev, [m.id]: { type: m.type, severity: m.severity || 'medium', status: 'ACTIVE' } }))
      })
    }
    if (msg.type === 'map_update') {
      MapStateManager.receive(msg)
      if (msg.action === 'add_marker' && msg.incident_id && msg.payload) {
        setIncidents(prev => ({ ...prev, [msg.incident_id]: { type: msg.payload.type, severity: msg.payload.severity, status: msg.payload.status || 'ACTIVE' } }))
      }
    }
    if (msg.type === 'zones' && Array.isArray(msg.data)) {
      msg.data.forEach((zone) => MapStateManager.receive({ type: 'map_update', action: 'add_zone', incident_id: zone.incident_id || null, payload: zone }))
    }
    if (msg.type === 'survivors' && Array.isArray(msg.data)) {
      msg.data.forEach((s) => MapStateManager.receive({ type: 'map_update', action: 'add_survivor', incident_id: null,
        payload: { id: s.id, lat: s.lat, lon: s.lon, survivor_count: s.count, probability: s.probability, detected_by: 'swarm', time: new Date().toLocaleTimeString() } }))
    }
    if (msg.type === 'advisory' && msg.data) {
      setAdvisory({ data: msg.data, ts: new Date().toISOString() })
      setAgentStates(prev => ({ ...prev, A3: 'done' }))
    }
    if (msg.type === 'agent_stream') {
      const d = msg.data || {}
      const rawId = (d.agent_id || '').toLowerCase()
      let agent = 'SYS'
      if (rawId.startsWith('agent-1')) agent = 'A1'
      else if (rawId.startsWith('agent-2')) agent = 'A2'
      else if (rawId.startsWith('agent-3')) agent = 'A3'

      // Update agent states
      const ev = d.event || ''
      setAgentStates(prev => {
        const next = { ...prev }
        if (agent === 'A1') {
          if (ev === 'started' || ev === 'survey_started') next.A1 = 'active'
          if (ev === 'classified') next.A1 = 'done'
          if (ev === 'error') next.A1 = 'error'
        }
        if (agent === 'A2') {
          if (ev === 'started' || ev === 'swarm_deployed') next.A2 = 'active'
          if (ev === 'findings_reported') next.A2 = 'done'
          if (ev === 'error') next.A2 = 'error'
        }
        if (agent === 'A3') {
          if (ev === 'started') next.A3 = 'active'
          if (ev === 'advisory_issued' || ev === 'advisory_updated') next.A3 = 'done'
          if (ev === 'error') next.A3 = 'error'
        }
        return next
      })

      const content = typeof d.content === 'string' ? d.content : JSON.stringify(d.content)
      addFeedEntry({ id: `${Date.now()}-${Math.random()}`, agent, event: ev, content, ts: new Date().toTimeString().slice(0, 8) })
    }
  }, [addFeedEntry]))

  function handleLocationSelect(coords) {
    setCapturedCoords(coords)
    setIsSelectingLocation(false)
  }

  function handleMissionStart() {
    setAgentStates({ A1: 'idle', A2: 'idle', A3: 'idle' })
    setFeedEntries([])
    setAdvisory(null)
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden', background: '#000' }}>
      <Map
        isSelectingLocation={isSelectingLocation}
        onLocationSelect={handleLocationSelect}
        incidents={incidents}
        systemStatus={systemStatus}
      />
      <SidePanel
        wsConnected={wsConnected}
        systemStatus={systemStatus}
        isSelectingLocation={isSelectingLocation}
        onStartSelect={() => setIsSelectingLocation(true)}
        capturedCoords={capturedCoords}
        setCapturedCoords={setCapturedCoords}
        agentStates={agentStates}
        feedEntries={feedEntries}
        advisory={advisory}
        onMissionStart={handleMissionStart}
      />
    </div>
  )
}

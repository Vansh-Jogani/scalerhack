import { useState, useEffect, useRef, useCallback } from 'react'
import Map from './Map'
import CommandDashboard from './CommandDashboard'
import MapStateManager from './MapStateManager'

const MAX_AGENT_ENTRIES = 150

function useReconnectingWS(path, onMessage) {
  const cbRef = useRef(onMessage)
  cbRef.current = onMessage
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let stopped = false
    function connect() {
      const url = `ws://${window.location.host}${path}`
      const ws = new WebSocket(url)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        try { cbRef.current(JSON.parse(e.data)) } catch {}
      }
      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        if (!stopped) setTimeout(connect, 2000)
      }
      ws.onerror = () => ws.close()
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
  const [agentEntries, setAgentEntries] = useState([])

  const systemStatus = Object.values(incidents).some(i => i.status === 'EMERGENCY')
    ? 'EMERGENCY' : Object.values(incidents).length > 0 ? 'ACTIVE' : 'NOMINAL'

  const handleAdvisoryUpdate = useCallback((text, timestamp) => {
    setAdvisory({ text, timestamp })
  }, [])

  const addAgentEntry = useCallback((entry) => {
    setAgentEntries((prev) => {
      const next = [entry, ...prev]
      return next.length > MAX_AGENT_ENTRIES ? next.slice(0, MAX_AGENT_ENTRIES) : next
    })
  }, [])

  const { connected, send } = useReconnectingWS('/ws', useCallback((msg) => {
    if (msg.type === 'hello') {
      if (msg.bases) MapStateManager.renderBases(msg.bases)
    }
    if (msg.type === 'bases' && Array.isArray(msg.data)) MapStateManager.renderBases(msg.data)

    if (msg.type === 'map_update') {
      MapStateManager.receive(msg)
      if (msg.action === 'add_marker' && msg.incident_id && msg.payload) {
        setIncidents(prev => ({ ...prev, [msg.incident_id]: { type: msg.payload.type, severity: msg.payload.severity, status: msg.payload.status || 'ACTIVE' } }))
      }
    }

    if (msg.type === 'telemetry') {
      MapStateManager.receive({ type: 'map_update', action: 'update_drone', incident_id: null, payload: msg.data })
    }

    if (msg.type === 'markers') {
      msg.data?.forEach((m) => {
        MapStateManager.receive({
          type: 'map_update', action: 'add_marker', incident_id: m.id,
          payload: { lat: m.lat, lon: m.lon, type: m.type, severity: m.severity || 'MEDIUM', status: 'ACTIVE' },
        })
        setIncidents((prev) => ({
          ...prev,
          [m.id]: { type: m.type, severity: m.severity || 'medium', status: 'ACTIVE' },
        }))
      })
    }

    if (msg.type === 'advisory' && msg.data) {
      setAdvisory({ text: msg.data, timestamp: new Date().toISOString() })
    }

    if (msg.type === 'zones' && Array.isArray(msg.data)) {
      msg.data.forEach((zone) => MapStateManager.receive({ type: 'map_update', action: 'add_zone', incident_id: zone.incident_id || null, payload: zone }))
    }

    if (msg.type === 'survivors' && Array.isArray(msg.data)) {
      msg.data.forEach((s) => MapStateManager.receive({ type: 'map_update', action: 'add_survivor', incident_id: null,
        payload: { id: s.id, lat: s.lat, lon: s.lon, survivor_count: s.count, probability: s.probability, detected_by: 'swarm', time: new Date().toLocaleTimeString() } }))
    }

    if (msg.type === 'agent_stream') {
      const d = msg.data || {}
      const rawId = (d.agent_id || '').toLowerCase()
      let agent = 'ORCHESTRATOR'
      if (rawId.startsWith('agent-1')) agent = 'AGENT_1'
      else if (rawId.startsWith('agent-2')) agent = 'AGENT_2'
      else if (rawId.startsWith('agent-3')) agent = 'AGENT_3'
      else if (rawId.startsWith('agent-4')) agent = 'AGENT_4'
      else if (rawId === 'world') agent = 'ORCHESTRATOR'
      else if (rawId.includes('orchestrator')) agent = 'ORCHESTRATOR'

      if (d.event === 'suppression_active' && d.content?.incident_id) {
        const sev = d.content.severity || 'medium'
        const dur = sev === 'low' ? 12000 : sev === 'high' ? 18000 : 15000
        MapStateManager.startFireSuppression(d.content.incident_id, dur, sev)
      }
      if (d.event === 'suppression_drop' && d.content?.lat != null && d.content?.lon != null) {
        MapStateManager.triggerSuppressionDrop(d.content.lat, d.content.lon)
      }

      const content = typeof d.content === 'string' ? d.content : JSON.stringify(d.content)
      addAgentEntry({
        id: `${Date.now()}-${Math.random()}`,
        agent,
        event: d.event || '',
        content,
        ts: new Date().toTimeString().slice(0, 8),
      })

      if ((agent === 'AGENT_3' && d.event === 'advisory_issued') || d.event === 'advisory_updated') {
        const advisoryContent = typeof d.content === 'object' ? d.content : content
        handleAdvisoryUpdate(advisoryContent, new Date().toISOString())
      }
    }
  }, [addAgentEntry, handleAdvisoryUpdate]))

  function handleLocationSelect(coords) {
    setCapturedCoords(coords)
    setIsSelectingLocation(false)
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden', background: '#000' }}>
      <Map
        isSelectingLocation={isSelectingLocation}
        onLocationSelect={handleLocationSelect}
        incidents={incidents}
        systemStatus={systemStatus}
      />
      <div style={{
        position: 'absolute', top: 0, right: 0,
        width: '40%', height: '100%',
        display: 'flex', flexDirection: 'column',
        borderLeft: '1px solid var(--border)',
        background: '#0A0E14',
        flexShrink: 0,
      }}>
        <CommandDashboard
          isSelectingLocation={isSelectingLocation}
          onStartSelectLocation={() => setIsSelectingLocation(true)}
          capturedCoords={capturedCoords}
          activeIncidentType={Object.values(incidents)[0]?.type || null}
          advisory={advisory}
          onAdvisoryUpdate={handleAdvisoryUpdate}
          connected={connected}
          agentEntries={agentEntries}
          onSendCommand={send}
        />
      </div>
    </div>
  )
}

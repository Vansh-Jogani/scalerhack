import { useState, useEffect, useRef, useCallback } from 'react'
import Map from './Map'
import CommandDashboard from './CommandDashboard'
import MapStateManager from './MapStateManager'

const MAX_ENTRIES = 150

function deriveSystemStatus(incidents) {
  const vals = Object.values(incidents)
  if (vals.some((i) => i.status === 'EMERGENCY')) return 'EMERGENCY'
  if (vals.length > 0) return 'ACTIVE'
  return 'NOMINAL'
}

function useReconnectingWS(path, onMessage) {
  const cbRef = useRef(onMessage)
  cbRef.current = onMessage
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let stopped = false
    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${protocol}://${window.location.host}${path}`
      const ws = new WebSocket(url)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        try { cbRef.current(JSON.parse(e.data)) } catch (_) {}
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
    }
  }, [])

  return { connected, send }
}

function App() {
  const [incidents, setIncidents] = useState({})
  const [isSelectingLocation, setIsSelectingLocation] = useState(false)
  const [capturedCoords, setCapturedCoords] = useState(null)
  const [advisory, setAdvisory] = useState(null)
  const [agentEntries, setAgentEntries] = useState([])

  const activeIncidentType = Object.values(incidents)[0]?.type || null
  const systemStatus = deriveSystemStatus(incidents)

  const { connected: wsConnected, send: wsSend } = useReconnectingWS('/ws', useCallback((msg) => {
    if (msg.type === 'map_update') {
      MapStateManager.receive(msg)
      if (msg.action === 'add_marker' && msg.incident_id && msg.payload) {
        setIncidents((prev) => ({
          ...prev,
          [msg.incident_id]: {
            type: msg.payload.type,
            severity: msg.payload.severity,
            status: msg.payload.status || 'ACTIVE',
          },
        }))
      } else if (msg.action === 'remove_marker' && msg.incident_id) {
        setIncidents((prev) => {
          const next = { ...prev }
          delete next[msg.incident_id]
          return next
        })
      }
    }
    if (msg.type === 'telemetry') {
      MapStateManager.receive({
        type: 'map_update',
        action: 'update_drone',
        incident_id: null,
        payload: msg.data,
      })
    }
    if (msg.type === 'markers') {
      msg.data?.forEach((m) => {
        MapStateManager.receive({
          type: 'map_update',
          action: 'add_marker',
          incident_id: m.id,
          payload: { lat: m.lat, lon: m.lon, type: m.type, severity: m.severity || 'MEDIUM', status: 'ACTIVE' },
        })
        setIncidents((prev) => ({
          ...prev,
          [m.id]: { type: m.type, severity: m.severity || 'MEDIUM', status: 'ACTIVE' },
        }))
      })
    }
    if (msg.type === 'advisory') {
      setAdvisory(msg.data || {})
    }
    if (msg.type === 'agent_stream') {
      const d = msg.data || {}
      const agent = (d.agent_id || '')
        .replace('agent-', 'AGENT_')
        .replace('orchestrator', 'ORCHESTRATOR')
        .toUpperCase()
      const content = typeof d.content === 'string' ? d.content : JSON.stringify(d.content)
      setAgentEntries((prev) => {
        const next = [{
          id: `${Date.now()}-${Math.random()}`,
          agent,
          event: d.event || '',
          content,
          ts: new Date().toTimeString().slice(0, 8),
        }, ...prev]
        return next.length > MAX_ENTRIES ? next.slice(0, MAX_ENTRIES) : next
      })
    }
  }, []))

  function handleStartSelectLocation() {
    setIsSelectingLocation(true)
  }

  function handleLocationSelect(lngLat) {
    setCapturedCoords(lngLat)
    setIsSelectingLocation(false)
  }

  return (
    <div style={{
      display: 'flex',
      width: '100vw',
      height: '100vh',
      overflow: 'hidden',
      background: 'var(--bg)',
    }}>
      <div style={{ width: '60%', height: '100%', position: 'relative', flexShrink: 0 }}>
        <Map
          isSelectingLocation={isSelectingLocation}
          onLocationSelect={handleLocationSelect}
          incidents={incidents}
          systemStatus={systemStatus}
        />
      </div>

      <div style={{
        width: '40%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--border)',
        background: '#0A0E14',
        flexShrink: 0,
      }}>
        <CommandDashboard
          isSelectingLocation={isSelectingLocation}
          onStartSelectLocation={handleStartSelectLocation}
          capturedCoords={capturedCoords}
          activeIncidentType={activeIncidentType}
          advisory={advisory}
          agentEntries={agentEntries}
          wsConnected={wsConnected}
          onSend={wsSend}
        />
      </div>
    </div>
  )
}

export default App

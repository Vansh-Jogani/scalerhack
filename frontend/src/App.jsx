import { useState, useEffect, useRef, useCallback } from 'react'
import Map from './Map'
import CommandDashboard from './CommandDashboard'
import MapStateManager from './MapStateManager'

function deriveSystemStatus(incidents) {
  const vals = Object.values(incidents)
  if (vals.some((i) => i.status === 'EMERGENCY')) return 'EMERGENCY'
  if (vals.length > 0) return 'ACTIVE'
  return 'NOMINAL'
}

function useReconnectingWS(path, onMessage) {
  const cbRef = useRef(onMessage)
  cbRef.current = onMessage
  useEffect(() => {
    let ws
    let stopped = false
    function connect() {
      const url = `ws://${window.location.hostname}:8080${path}`
      ws = new WebSocket(url)
      ws.onmessage = (e) => {
        try { cbRef.current(JSON.parse(e.data)) } catch {}
      }
      ws.onclose = () => { if (!stopped) setTimeout(connect, 2000) }
    }
    connect()
    return () => { stopped = true; ws?.close() }
  }, [path])
}

function App() {
  const [incidents, setIncidents] = useState({})
  const [isSelectingLocation, setIsSelectingLocation] = useState(false)
  const [capturedCoords, setCapturedCoords] = useState(null)
  const [advisory, setAdvisory] = useState(null)

  const activeIncidentType = Object.values(incidents)[0]?.type || null
  const systemStatus = deriveSystemStatus(incidents)

  useReconnectingWS('/ws', useCallback((msg) => {
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
      })
    }
  }, []))

  function handleAdvisoryUpdate(text, timestamp) {
    setAdvisory({ text, timestamp })
  }

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
          onAdvisoryUpdate={handleAdvisoryUpdate}
        />
      </div>
    </div>
  )
}

export default App

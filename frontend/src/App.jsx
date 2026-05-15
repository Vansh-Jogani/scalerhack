import { useState, useEffect, useRef, useCallback } from 'react'
import './index.css'
import Map from './Map.jsx'
import AdminPanel from './AdminPanel.jsx'
import AgentFeed from './AgentFeed.jsx'
import AdvisoryPanel from './AdvisoryPanel.jsx'
import MapStateManager from './MapStateManager.js'

const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 30000]

function useReconnectingWS(path, onMessage) {
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const timerRef = useRef(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(`ws://${window.location.host}${path}`)
    wsRef.current = ws

    ws.onopen = () => { retryRef.current = 0 }
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        onMessageRef.current(msg)
      } catch {
        // ignore malformed frames
      }
    }
    ws.onclose = () => {
      wsRef.current = null
      const delay = BACKOFF_STEPS[Math.min(retryRef.current, BACKOFF_STEPS.length - 1)]
      retryRef.current += 1
      timerRef.current = setTimeout(connect, delay)
    }
    ws.onerror = () => ws.close()
  }, [path])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}

function deriveSystemStatus(incidents) {
  const vals = Object.values(incidents)
  if (vals.length === 0) return 'NOMINAL'
  const severities = vals.map((v) => v.severity?.toUpperCase())
  if (severities.includes('CRITICAL') || severities.includes('HIGH')) return 'EMERGENCY'
  return 'ACTIVE'
}

function App() {
  const [incidents, setIncidents] = useState({})
  const [advisory, setAdvisory] = useState(null)
  const [isSelectingLocation, setIsSelectingLocation] = useState(false)
  const [capturedCoords, setCapturedCoords] = useState(null)

  // Active incident type for Agent 2 colour coding
  const activeIncidentType = Object.values(incidents)[0]?.type || null
  const systemStatus = deriveSystemStatus(incidents)

  // ws/map — all events go through MapStateManager
  useReconnectingWS('/ws/map', useCallback((msg) => {
    if (msg.type === 'map_update') {
      MapStateManager.receive(msg)
      // Mirror incident metadata into React state for UI counters
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
    // Also handle legacy telemetry / markers from the existing ws endpoint
    // (backend may still broadcast these during Stage 1 WS)
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

  // ws/agents — advisory extraction is handled inside AgentFeed
  // We keep the connection here too so App can react to agent events if needed

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
      {/* LEFT: Map — 60% */}
      <div style={{ width: '60%', height: '100%', position: 'relative', flexShrink: 0 }}>
        <Map
          isSelectingLocation={isSelectingLocation}
          onLocationSelect={handleLocationSelect}
          incidents={incidents}
          systemStatus={systemStatus}
        />
      </div>

      {/* RIGHT: Dashboard — 40% */}
      <div style={{
        width: '40%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--border)',
        background: 'var(--surface)',
        flexShrink: 0,
      }}>
        {/* TOP THIRD: Admin */}
        <div style={{ flex: '0 0 33.333%', borderBottom: '1px solid var(--border)', overflow: 'hidden' }}>
          <AdminPanel
            isSelectingLocation={isSelectingLocation}
            onStartSelectLocation={handleStartSelectLocation}
            capturedCoords={capturedCoords}
          />
        </div>

        {/* MIDDLE THIRD: Agent feed */}
        <div style={{ flex: '0 0 33.333%', borderBottom: '1px solid var(--border)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <AgentFeed
            onAdvisoryUpdate={handleAdvisoryUpdate}
            activeIncidentType={activeIncidentType}
          />
        </div>

        {/* BOTTOM THIRD: Advisory */}
        <div style={{ flex: '0 0 33.333%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <AdvisoryPanel advisory={advisory} />
        </div>
      </div>
    </div>
  )
}

export default App

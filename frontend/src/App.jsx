import { useState, useEffect, useRef, useCallback } from 'react'
import Map from './Map'
import AdminPanel from './AdminPanel'
import AgentFeed from './AgentFeed'
import AdvisoryPanel from './AdvisoryPanel'
import MapStateManager from './MapStateManager.js'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function deriveSystemStatus(incidents) {
  const vals = Object.values(incidents)
  if (vals.length === 0) return 'NOMINAL'
  if (vals.some((v) => v.severity === 'CRITICAL')) return 'EMERGENCY'
  return 'ACTIVE'
}

// ─── App ──────────────────────────────────────────────────────────────────────

function App() {
  const [incidents, setIncidents] = useState({})
  const [isSelectingLocation, setIsSelectingLocation] = useState(false)
  const [capturedCoords, setCapturedCoords] = useState(null)
  const [advisory, setAdvisory] = useState(null)
  const wsRef = useRef(null)
  const retryRef = useRef(null)

  const activeIncidentType = Object.values(incidents)[0]?.type || null
  const systemStatus = deriveSystemStatus(incidents)

  // ── WebSocket connection to backend (/ws) ──
  const handleMessage = useCallback((msg) => {
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
          [m.id]: {
            type: m.type,
            severity: m.severity || 'MEDIUM',
            status: 'ACTIVE',
          },
        }))
      })
    }
    if (msg.type === 'advisory') {
      setAdvisory({ text: msg.data?.text || '', timestamp: new Date().toISOString() })
    }
    if (msg.type === 'agent_stream') {
      // Dispatch as custom event for AgentFeed
      window.dispatchEvent(new CustomEvent('aria-agent-event', {
        detail: {
          agent: msg.data?.agent_id?.toUpperCase()?.replace('-', '_') || 'ORCHESTRATOR',
          text: msg.data?.content || msg.data?.event || '',
        },
      }))
    }
  }, [])

  useEffect(() => {
    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws`)
      wsRef.current = ws

      ws.onmessage = (evt) => {
        try {
          handleMessage(JSON.parse(evt.data))
        } catch (e) {
          console.warn('[App] WS parse error', e)
        }
      }

      ws.onclose = () => {
        wsRef.current = null
        retryRef.current = setTimeout(connect, 2000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [handleMessage])

  // ── Callbacks ──
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
      {/* LEFT: Full-height Map — 60% */}
      <div style={{ width: '60%', height: '100%', position: 'relative', flexShrink: 0 }}>
        <Map
          isSelectingLocation={isSelectingLocation}
          onLocationSelect={handleLocationSelect}
          incidents={incidents}
          systemStatus={systemStatus}
        />
      </div>

      {/* RIGHT: Three-panel dashboard — 40% */}
      <div style={{
        width: '40%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--border)',
        background: 'var(--surface)',
        flexShrink: 0,
      }}>
        {/* TOP THIRD: Incident Command */}
        <div style={{ flex: '0 0 33.333%', borderBottom: '1px solid var(--border)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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

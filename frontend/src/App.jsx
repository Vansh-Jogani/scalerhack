import { useState, useEffect, useRef } from 'react'
import Map from './Map'
import AgentStream from './AgentStream'
import AdvisoryPanel from './AdvisoryPanel'
import DroneStatus from './DroneStatus'

function App() {
  const [droneData, setDroneData] = useState({})
  const [markers, setMarkers] = useState([])
  const [agentStream, setAgentStream] = useState([])
  const [advisory, setAdvisory] = useState(null)
  const ws = useRef(null)

  const activeIncidentType = Object.values(incidents)[0]?.type || null
  const systemStatus = deriveSystemStatus(incidents)

  useReconnectingWS('/ws/map', useCallback((msg) => {
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

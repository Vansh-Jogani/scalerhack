import { useState, useEffect } from 'react'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_TYPES, SEVERITY_LEVELS } from './constants.js'

const TYPE_META = DISASTER_TYPES.map((t) => ({
  key: t,
  label: DISASTER_LABELS[t],
  color: DISASTER_COLORS[t],
}))

function AdminPanel({ isSelectingLocation, onStartSelectLocation, capturedCoords }) {
  const [coords, setCoords] = useState(null)
  const [selectedType, setSelectedType] = useState(null)
  const [selectedSeverity, setSelectedSeverity] = useState(null)
  const [deployStatus, setDeployStatus] = useState('idle') // idle | dispatching | active | failed

  // Sync captured coords from App/Map when a location is selected
  useEffect(() => {
    if (capturedCoords) setCoords(capturedCoords)
  }, [capturedCoords])

  const canDeploy = coords && selectedType && selectedSeverity && deployStatus === 'idle'
  const accentColor = selectedType ? DISASTER_COLORS[selectedType] : '#E8EDF5'

  async function deploy() {
    if (!canDeploy) return
    setDeployStatus('dispatching')
    try {
      const res = await fetch('/api/incident/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: coords.lat,
          lon: coords.lon,
          type: selectedType.toLowerCase(),
          severity: selectedSeverity.toLowerCase(),
        }),
      })
      if (res.ok) {
        setDeployStatus('active')
        setTimeout(() => setDeployStatus('idle'), 4000)
      } else {
        setDeployStatus('failed')
        setTimeout(() => setDeployStatus('idle'), 3000)
      }
    } catch {
      setDeployStatus('failed')
      setTimeout(() => setDeployStatus('idle'), 3000)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--surface)' }}>
      <div className="panel-header">
        INCIDENT COMMAND
      </div>

      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Location select */}
        <div>
          <div style={{ marginBottom: 5, fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'var(--font-display)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Trigger Location
          </div>
          <button
            onClick={onStartSelectLocation}
            style={{
              width: '100%',
              padding: '6px 12px',
              background: isSelectingLocation ? 'rgba(255,255,255,0.08)' : 'transparent',
              border: `1px solid ${isSelectingLocation ? 'var(--text-primary)' : 'var(--border)'}`,
              borderRadius: 2,
              color: isSelectingLocation ? 'var(--text-primary)' : 'var(--text-secondary)',
              fontFamily: 'var(--font-display)',
              fontSize: 12,
              fontWeight: 600,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {isSelectingLocation ? '▶ CLICK MAP TO PLACE' : '⊕ SELECT LOCATION'}
          </button>

          {coords && (
            <div
              style={{
                marginTop: 6,
                padding: '5px 10px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 2,
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--text-primary)',
                letterSpacing: '0.05em',
              }}
            >
              LAT {coords.lat.toFixed(4)}{'  '}LON {coords.lon.toFixed(4)}
            </div>
          )}
        </div>

        {/* Disaster type */}
        <div>
          <div style={{ marginBottom: 5, fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'var(--font-display)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Disaster Type
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {TYPE_META.map(({ key, label, color }) => (
              <button
                key={key}
                className={`type-pill${selectedType === key ? ' selected' : ''}`}
                style={{ color, borderColor: color }}
                onClick={() => setSelectedType(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Severity */}
        <div>
          <div style={{ marginBottom: 5, fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'var(--font-display)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Severity
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {SEVERITY_LEVELS.map((sev) => (
              <button
                key={sev}
                className={`severity-btn${selectedSeverity === sev ? ' selected' : ''}`}
                onClick={() => setSelectedSeverity(sev)}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>

        {/* Deploy */}
        <div style={{ marginTop: 2 }}>
          <button
            className="deploy-btn"
            disabled={!canDeploy}
            onClick={deploy}
            style={{
              background: canDeploy ? accentColor : 'var(--surface-2)',
              color: canDeploy ? '#0A0E14' : 'var(--text-secondary)',
            }}
          >
            {deployStatus === 'dispatching' && <><div className="spinner" /> DISPATCHING...</>}
            {deployStatus === 'active' && '✓ INCIDENT ACTIVE'}
            {deployStatus === 'failed' && '✕ DEPLOY FAILED'}
            {deployStatus === 'idle' && 'DEPLOY INCIDENT'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default AdminPanel

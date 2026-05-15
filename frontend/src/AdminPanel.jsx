import { useState, useEffect } from 'react'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_TYPES, SEVERITY_LEVELS } from './constants.js'
import { setDrawColor, clearDrawPolygon } from './Map.jsx'

const TYPE_META = DISASTER_TYPES.map((t) => ({
  key: t,
  label: DISASTER_LABELS[t],
  color: DISASTER_COLORS[t],
}))

function AdminPanel({ isSelectingLocation, onStartSelectLocation, capturedCoords }) {
  const [coords, setCoords] = useState(null)       // { lat, lon, radius_m, vertices }
  const [selectedType, setSelectedType] = useState(null)
  const [selectedSeverity, setSelectedSeverity] = useState(null)
  const [deployStatus, setDeployStatus] = useState('idle')

  // When Map closes the circle it fires onLocationSelect → App sets capturedCoords
  useEffect(() => {
    if (capturedCoords) setCoords(capturedCoords)
  }, [capturedCoords])

  // Keep circle colour in sync with selected disaster type
  useEffect(() => {
    if (selectedType) setDrawColor(DISASTER_COLORS[selectedType])
  }, [selectedType])

  const hasZone = coords?.radius_m > 0
  const canDeploy = coords && selectedType && selectedSeverity && deployStatus === 'idle'
  const accentColor = selectedType ? DISASTER_COLORS[selectedType] : '#E8EDF5'

  function handleClear() {
    clearDrawPolygon()
    setCoords(null)
  }

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
          zone_radius_m: coords.radius_m ?? null,
          zone_polygon: coords.vertices ?? null,
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

  const label10 = {
    fontSize: 10,
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-display)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    marginBottom: 5,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--surface)' }}>
      <div className="panel-header">INCIDENT COMMAND</div>

      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>

        {/* ── Zone draw ── */}
        <div>
          <div style={label10}>Trigger Zone</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={onStartSelectLocation}
              style={{
                flex: 1,
                padding: '6px 10px',
                background: isSelectingLocation ? 'rgba(255,255,255,0.08)' : 'transparent',
                border: `1px solid ${isSelectingLocation ? accentColor : 'var(--border)'}`,
                borderRadius: 2,
                color: isSelectingLocation ? accentColor : 'var(--text-secondary)',
                fontFamily: 'var(--font-display)',
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {isSelectingLocation ? '◎ DRAWING...' : '◎ DRAW ZONE'}
            </button>

            {coords && (
              <button
                onClick={handleClear}
                style={{
                  padding: '6px 10px',
                  background: 'transparent',
                  border: '1px solid var(--critical)',
                  borderRadius: 2,
                  color: 'var(--critical)',
                  fontFamily: 'var(--font-display)',
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                CLEAR
              </button>
            )}
          </div>

          {/* Zone summary */}
          {coords && (
            <div style={{
              marginTop: 6,
              padding: '5px 10px',
              background: 'var(--surface-2)',
              border: `1px solid ${hasZone ? accentColor : 'var(--border)'}`,
              borderRadius: 2,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-primary)',
              letterSpacing: '0.04em',
              lineHeight: 1.8,
            }}>
              <span style={{ color: 'var(--text-secondary)' }}>CTR  </span>
              {coords.lat.toFixed(4)} / {coords.lon.toFixed(4)}
              {hasZone && (
                <>
                  <br />
                  <span style={{ color: 'var(--text-secondary)' }}>RAD  </span>
                  {coords.radius_m >= 1000
                    ? (coords.radius_m / 1000).toFixed(2) + ' km'
                    : coords.radius_m + ' m'}
                </>
              )}
            </div>
          )}

          {isSelectingLocation && (
            <div style={{
              marginTop: 5,
              fontSize: 10,
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.03em',
            }}>
              {!coords ? 'Click to set centre' : 'Click again to set radius'}
            </div>
          )}
        </div>

        {/* ── Disaster type ── */}
        <div>
          <div style={label10}>Disaster Type</div>
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

        {/* ── Severity ── */}
        <div>
          <div style={label10}>Severity</div>
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

        {/* ── Deploy ── */}
        <div>
          <button
            className="deploy-btn"
            disabled={!canDeploy}
            onClick={deploy}
            style={{
              background: canDeploy ? accentColor : 'var(--surface-2)',
              color: canDeploy ? '#0A0E14' : 'var(--text-secondary)',
            }}
          >
            {deployStatus === 'dispatching' && <><div className="spinner" />&nbsp;DISPATCHING...</>}
            {deployStatus === 'active'      && '✓ INCIDENT ACTIVE'}
            {deployStatus === 'failed'      && '✕ DEPLOY FAILED'}
            {deployStatus === 'idle'        && 'DEPLOY INCIDENT'}
          </button>
        </div>

      </div>
    </div>
  )
}

export default AdminPanel

import { useState, useEffect, useRef } from 'react'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_TYPES, SEVERITY_LEVELS, DISASTER_COLOR_MAP } from './constants.js'
import { setDrawColor, clearDrawPolygon } from './Map.jsx'
import responseCentres from './data/response_centres.json'
import { findNearestCentre } from './DispatchAnimation.js'

function formatContent(raw) {
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (typeof obj !== 'object' || obj === null) return raw
    return Object.entries(obj).map(([k, v]) => {
      const val = typeof v === 'object' ? JSON.stringify(v) : String(v)
      return (
        <div key={k} style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ color: '#7A9AB8', flexShrink: 0 }}>{k}</span>
          <span style={{ color: '#FFFFFF', wordBreak: 'break-all' }}>{val}</span>
        </div>
      )
    })
  } catch {
    return <span style={{ color: '#FFFFFF' }}>{raw}</span>
  }
}

const SEV_COLORS = { LOW: '#FFE566', MEDIUM: '#FFAA00', HIGH: '#FF5500', CRITICAL: '#CC1A1A' }

const TYPE_META = DISASTER_TYPES.map((t) => ({  key: t,
  label: DISASTER_LABELS[t],
  color: DISASTER_COLORS[t],
}))

const AGENT_LABELS = {
  ORCHESTRATOR: 'ORC',
  AGENT_1:      'A-1',
  AGENT_2:      'A-2',
  AGENT_3:      'A-3',
  AGENT_4:      'A-4',
}

const AGENT_COLORS = {
  AGENT_1: '#7B68EE',
  AGENT_2: null,
  AGENT_3: '#00FF88',
  AGENT_4: '#FF6B35',
  ORCHESTRATOR: '#6A8AAA',
}

const MAX_ENTRIES = 150

// ─── sub-component: section label ───────────────────────────────────────────

function SectionLabel({ children, right }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 7,
    }}>
      <span style={{
        fontSize: 11,
        fontFamily: 'var(--font-display)',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: '#A8BECE',
      }}>{children}</span>
      {right && <span style={{ fontSize: 9, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{right}</span>}
    </div>
  )
}

// ─── sub-component: advisory block ──────────────────────────────────────────

function Advisory({ advisory }) {
  if (!advisory || (!advisory.text && !advisory.sections)) return (
    <div style={{
      padding: '10px 0',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: '#7A9AB8',
      letterSpacing: '0.06em',
      display: 'flex',
      alignItems: 'center',
      gap: 6,
    }}>
      <span style={{ color: '#7A9AB8' }}>▮</span>
      AWAITING AGENT 3 REPORT
    </div>
  )

  const s = advisory.sections || null

  const splitLines = (str) =>
    (str || '').split('\n').map((l) => l.trim()).filter(Boolean)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {advisory.timestamp && (
        <div style={{ fontSize: 9, color: '#7A9AB8', fontFamily: 'var(--font-mono)' }}>
          {new Date(advisory.timestamp).toLocaleTimeString()}
        </div>
      )}

      {s ? (
        <>
          {s.situation_summary && (
            <AdvisoryBlock label="Situation" color="var(--text-primary)">
              {s.situation_summary}
            </AdvisoryBlock>
          )}
          {s.immediate_actions && (
            <AdvisoryBlock label="Immediate Actions">
              {splitLines(s.immediate_actions).map((a, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 3 }}>
                  <span style={{ color: '#00FF88', flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</span>
                  <span>{a.replace(/^\d+[.)]\s*/, '')}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {s.risk_flags && (
            <AdvisoryBlock label="Risk Flags" color="#FFB800">
              {splitLines(s.risk_flags).map((f, i) => (
                <div key={i} style={{ display: 'flex', gap: 5 }}>
                  <span style={{ color: '#FFB800' }}>⚠</span>
                  <span>{f.replace(/^[-•]\s*/, '')}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {s.exclusion_zones && (
            <AdvisoryBlock label="Exclusion Zones" color="#FF3B3B">
              <div style={{ color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>{s.exclusion_zones}</div>
            </AdvisoryBlock>
          )}
          {s.resource_requirements && (
            <AdvisoryBlock label="Resources">
              {splitLines(s.resource_requirements).map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: 5 }}>
                  <span style={{ color: '#5A7A9A' }}>·</span>
                  <span>{r.replace(/^[-•]\s*/, '')}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {s.monitoring && (
            <AdvisoryBlock label="Monitoring">{s.monitoring}</AdvisoryBlock>
          )}
        </>
      ) : (
        <p style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: '#FFFFFF',
          lineHeight: 1.8,
          whiteSpace: 'pre-wrap',
        }}>{text}</p>
      )}

      {structured && (
        <>
          {structured.situation_summary && (
            <AdvisoryBlock label="Situation" color="#A8BECE">
              {structured.situation_summary}
            </AdvisoryBlock>
          )}
          {structured.immediate_actions?.length > 0 && (
            <AdvisoryBlock label="Immediate Actions">
              {structured.immediate_actions.map((a, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 3 }}>
                  <span style={{ color: '#00FF88', flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</span>
                  <span>{a}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {structured.risk_flags?.length > 0 && (
            <AdvisoryBlock label="Risk Flags" color="#FFB800">
              {structured.risk_flags.map((f, i) => (
                <div key={i} style={{ display: 'flex', gap: 5 }}>
                  <span style={{ color: '#FFB800' }}>⚠</span>
                  <span>{f}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {structured.exclusion_zones?.length > 0 && (
            <AdvisoryBlock label="Exclusion Zones" color="#FF3B3B">
              {structured.exclusion_zones.map((z, i) => (
                <div key={i} style={{ color: '#FF3B3B' }}>
                  {z.radius_m}m @ {z.lat?.toFixed(4)}, {z.lon?.toFixed(4)}
                  {z.reason && <span style={{ color: '#A8BECE' }}> — {z.reason}</span>}
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {structured.resource_requirements?.length > 0 && (
            <AdvisoryBlock label="Resources">
              {structured.resource_requirements.map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: 5 }}>
                  <span style={{ color: '#8AA0B4' }}>·</span>
                  <span>{r}</span>
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {structured.monitoring_status && (
            <AdvisoryBlock label="Monitoring">{structured.monitoring_status}</AdvisoryBlock>
          )}
        </>
      )}
    </div>
  )
}

function AdvisoryBlock({ label, color, children }) {
  return (
    <div>
      <div style={{
        fontSize: 9,
        fontFamily: 'var(--font-display)',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: color || '#A8BECE',
        marginBottom: 4,
      }}>{label}</div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: '#FFFFFF',
        lineHeight: 1.7,
      }}>{children}</div>
    </div>
  )
}

// ─── main component ───────────────────────────────────────────────────────────

export default function CommandDashboard({
  isSelectingLocation,
  onStartSelectLocation,
  capturedCoords,
  activeIncidentType,
  advisory,
  onAdvisoryUpdate,
  connected,
  agentEntries,
  onSendCommand,
}) {
  // ── Command state ──
  const [coords, setCoords] = useState(null)
  const [selectedType, setSelectedType] = useState(null)
  const [selectedSeverity, setSelectedSeverity] = useState(null)
  const [deployStatus, setDeployStatus] = useState('idle')
  const [controlsExpanded, setControlsExpanded] = useState(true)

  // ── Tab state ──
  const [tab, setTab] = useState('pipeline') // 'pipeline' | 'advisory'
  const feedRef = useRef(null)

  // ── Sync captured coords ──
  useEffect(() => { if (capturedCoords) setCoords(capturedCoords) }, [capturedCoords])

  // ── Sync circle colour ──
  useEffect(() => { if (selectedType) setDrawColor(DISASTER_COLORS[selectedType]) }, [selectedType])


  // ── Deploy ──
  const hasZone = coords?.radius_m > 0
  const canDeploy = coords && selectedType && selectedSeverity && deployStatus === 'idle'
  const accent = selectedType ? DISASTER_COLORS[selectedType] : 'var(--text-secondary)'

  function handleClear() { clearDrawPolygon(); setCoords(null); setControlsExpanded(true) }

  function deploy() {
    if (!canDeploy) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setDeployStatus('failed')
      setTimeout(() => setDeployStatus('idle'), 3000)
      return
    }
    setDeployStatus('dispatching')
    setControlsExpanded(false)
    try {
      wsRef.current.send(JSON.stringify({
        type: 'command',
        action: 'go',
        data: {
          area: {
            center: { lat: coords.lat, lon: coords.lon },
            radius_m: coords.radius_m ?? 200,
            boundary_polygon: coords.vertices ?? null,
          },
          disaster_type: selectedType.toLowerCase(),
          severity: selectedSeverity.toLowerCase(),
          dispatch_from: nearest ? { name: nearest.name, lat: nearest.lat, lon: nearest.lon } : null,
        },
      })
    if (sent) {
      setDeployStatus('active')
      setTimeout(() => setDeployStatus('idle'), 4000)
    } else {
      setDeployStatus('failed')
      setTimeout(() => setDeployStatus('idle'), 3000)
    }
  }

  // ─── render ────────────────────────────────────────────────────────────────
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: '#0A0E14',
      overflow: 'hidden',
    }}>

      {/* ── Panel header ── */}
      <div style={{
        padding: '10px 14px 9px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <span style={{
          fontSize: 13,
          fontFamily: 'var(--font-display)',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: '#E8EDF5',
          fontWeight: 700,
        }}>
          Incident Command
          {deployStatus === 'active' && !controlsExpanded && (
            <span style={{ marginLeft: 8, fontSize: 9, color: '#00FF88', fontWeight: 400 }}>● MISSION ACTIVE</span>
          )}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', color: connected ? 'var(--success)' : '#2A3545' }}>
            {connected ? '● LIVE' : '○ OFFLINE'}
          </span>
          <button onClick={() => setControlsExpanded(v => !v)} style={{
            background: 'transparent', border: '1px solid var(--border)', borderRadius: 2,
            color: '#7A8FA8', fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            padding: '2px 7px', lineHeight: 1,
          }} title={controlsExpanded ? 'Collapse controls' : 'Expand controls'}>
            {controlsExpanded ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {/* ── Command controls ── */}
      {controlsExpanded && <div style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 11,
        flexShrink: 0,
      }}>

        {/* Zone row */}
        <div>
          <SectionLabel>Trigger Zone</SectionLabel>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={onStartSelectLocation} style={{
              flex: 1,
              padding: '7px 10px',
              background: isSelectingLocation ? `${accent}12` : 'transparent',
              border: `1px solid ${isSelectingLocation ? accent : 'var(--border)'}`,
              borderRadius: 3,
              color: isSelectingLocation ? accent : '#C0CDD9',
              fontFamily: 'var(--font-display)',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.08em',
              cursor: 'pointer',
              transition: 'all 0.12s',
            }}>
              {isSelectingLocation ? '◎  DRAWING…' : '◎  DRAW ZONE'}
            </button>
            {coords && (
              <button onClick={handleClear} style={{
                padding: '7px 10px',
                background: 'transparent',
                border: '1px solid var(--critical)',
                borderRadius: 3,
                color: 'var(--critical)',
                fontFamily: 'var(--font-display)',
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.08em',
                cursor: 'pointer',
              }}>CLEAR</button>
            )}
          </div>

          {coords && (
            <div style={{
              marginTop: 6,
              padding: '6px 10px',
              background: '#111822',
              border: `1px solid ${hasZone ? accent : '#3A5070'}`,
              borderRadius: 3,
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: '#FFFFFF',
              letterSpacing: '0.04em',
              lineHeight: 1.9,
            }}>
              <span style={{ color: '#7A9AB8' }}>LAT  </span>{coords.lat.toFixed(5)}
              {'  '}
              <span style={{ color: '#7A9AB8' }}>LON  </span>{coords.lon.toFixed(5)}
              {hasZone && (<><br />
                <span style={{ color: '#7A9AB8' }}>RAD  </span>
                {coords.radius_m >= 1000 ? (coords.radius_m / 1000).toFixed(2) + ' km' : coords.radius_m + ' m'}
              </>)}
            </div>
          )}

          {isSelectingLocation && !coords && (
            <div style={{ marginTop: 5, fontSize: 10, color: '#8AA0B4', fontFamily: 'var(--font-mono)' }}>
              Click map to set centre
            </div>
          )}
        </div>

        {/* Type pills */}
        <div>
          <SectionLabel>Disaster Type</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {TYPE_META.map(({ key, label, color }) => (
              <button
                key={key}
                onClick={() => setSelectedType(key)}
                style={{
                  padding: '4px 9px',
                  background: selectedType === key ? `${color}22` : `${color}10`,
                  border: `1px solid ${selectedType === key ? color : `${color}66`}`,
                  borderRadius: 2,
                  color: selectedType === key ? color : `${color}BB`,
                  fontFamily: 'var(--font-display)',
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                  boxShadow: selectedType === key ? `0 0 8px ${color}33` : 'none',
                }}
              >{label}</button>
            ))}
          </div>
        </div>

        {/* Severity row */}
        <div>
          <SectionLabel>Severity</SectionLabel>
          <div style={{ display: 'flex', gap: 4 }}>
            {SEVERITY_LEVELS.map((sev) => {
              const c = SEV_COLORS[sev]
              const active = selectedSeverity === sev
              return (
                <button key={sev} onClick={() => setSelectedSeverity(sev)} style={{
                  flex: 1,
                  padding: '5px 0',
                  background: active ? `${c}22` : `${c}10`,
                  border: `1px solid ${active ? c : `${c}66`}`,
                  borderRadius: 2,
                  color: active ? c : `${c}BB`,
                  fontFamily: 'var(--font-display)',
                  fontSize: 9,
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                  boxShadow: active ? `0 0 8px ${c}33` : 'none',
                }}>{sev}</button>
              )
            })}
          </div>
        </div>

        {/* Deploy button */}
        <button
          disabled={!canDeploy}
          onClick={deploy}
          style={{
            width: '100%',
            padding: '9px',
            background: canDeploy ? accent : '#0A0E14',
            border: `1px solid ${canDeploy ? accent : '#1A2535'}`,
            borderRadius: 3,
            color: canDeploy ? '#0A0E14' : '#7A9AB8',
            fontFamily: 'var(--font-display)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            cursor: canDeploy ? 'pointer' : 'not-allowed',
            transition: 'all 0.15s',
            boxShadow: canDeploy ? `0 0 16px ${accent}40` : 'none',
          }}
        >
          {deployStatus === 'dispatching' && '⟳  DISPATCHING…'}
          {deployStatus === 'active'      && '✓  INCIDENT ACTIVE'}
          {deployStatus === 'failed'      && '✕  DEPLOY FAILED'}
          {deployStatus === 'idle'        && 'DEPLOY INCIDENT'}
        </button>
      </div>}

      {/* ── Tab bar ── */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        {[['pipeline', 'AGENT PIPELINE'], ['advisory', 'ADVISORY']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1,
            padding: '9px 0',
            background: 'transparent',
            border: 'none',
            borderBottom: `2px solid ${tab === id ? accent : 'transparent'}`,
            color: tab === id ? '#E8EDF5' : '#7A8FA8',
            fontFamily: 'var(--font-display)',
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            transition: 'color 0.12s',
            marginBottom: -1,
          }}>
            {label}
            {id === 'advisory' && advisory && (
              <span style={{ marginLeft: 5, color: '#00FF88' }}>●</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Pipeline tab ── */}
      {tab === 'pipeline' && (
        <div
          ref={feedRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column-reverse',
            padding: '4px 0',
          }}
        >
          {!connected && agentEntries.length === 0 && (
            <div style={{
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: '#7A9AB8',
              letterSpacing: '0.05em',
            }}>○  AWAITING BACKEND</div>
          )}
          {connected && agentEntries.length === 0 && (
            <div style={{
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: '#7A9AB8',
              display: 'flex',
              gap: 6,
            }}>
              AWAITING INCIDENT TRIGGER
              <span style={{ animation: 'blink-cursor 1s step-end infinite' }}>▮</span>
            </div>
          )}

          {agentEntries.map((e) => {
            const agentColor = e.agent === 'AGENT_2' && activeIncidentType
              ? DISASTER_COLOR_MAP[activeIncidentType] || '#FFB800'
              : AGENT_COLORS[e.agent] || null

            const isDecision = e.event === 'decision'
            const isDispatch = e.event === 'dispatch'
            const isReasoning = e.event === 'reasoning' || e.event === 'rationale'
            const isClassified = e.event === 'classified'
            const isSensorHit = e.event === 'sensor_hit'
            const isOrbit = e.event === 'orbit_started' || e.event === 'ring_complete' || e.event === 'ring_clear'
            const isRelief = e.agent === 'AGENT_4' && (e.event === 'relief_started' || e.event === 'drone_tasked' || e.event === 'alert_broadcast')

            const borderColor = isDispatch ? '#00FF88'
              : isDecision ? '#FFB800'
              : isRelief ? '#FF6B35'
              : isClassified ? '#00FF88'
              : isSensorHit ? '#00CC66'
              : isOrbit ? '#3A5A7A'
              : agentColor || 'transparent'

            return (
              <div key={e.id} style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 8,
                padding: (isDecision || isDispatch || isRelief) ? '7px 14px' : '5px 14px',
                borderLeft: `2px solid ${borderColor}`,
                borderBottom: '1px solid rgba(255,255,255,0.025)',
                background: isDispatch ? 'rgba(0,255,136,0.06)'
                  : isRelief ? 'rgba(255,107,53,0.06)'
                  : isDecision ? 'rgba(255,184,0,0.05)'
                  : 'transparent',
              }}>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-mono)',
                  color: '#6A8AA8',
                  flexShrink: 0,
                  letterSpacing: '0.02em',
                }}>{e.ts}</span>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-display)',
                  letterSpacing: '0.1em',
                  color: agentColor || '#7A9AB8',
                  fontWeight: 600,
                  flexShrink: 0,
                  minWidth: 28,
                }}>{AGENT_LABELS[e.agent] || e.agent}</span>
                {e.event && !isReasoning && (
                  <span style={{
                    fontSize: 9,
                    fontFamily: 'var(--font-display)',
                    letterSpacing: '0.08em',
                    color: isDispatch ? '#00FF88'
                      : isDecision ? '#FFB800'
                      : isClassified ? '#00CC66'
                      : '#7A9AB8',
                    flexShrink: 0,
                  }}>{e.event}</span>
                )}
                <div style={{
                  fontSize: (isDecision || isDispatch || isRelief) ? 12 : isReasoning ? 10 : 11,
                  fontFamily: 'var(--font-mono)',
                  color: isDispatch ? '#00FF88'
                    : isRelief ? '#FF6B35'
                    : isReasoning ? '#5A7A9A'
                    : isClassified ? '#00FF88'
                    : isSensorHit ? '#7FFFD4'
                    : isOrbit ? '#4A7A9A'
                    : '#FFFFFF',
                  lineHeight: 1.6,
                  wordBreak: 'break-word',
                  fontStyle: isReasoning ? 'italic' : 'normal',
                  fontWeight: (isDecision || isDispatch || isRelief) ? 700 : 'normal',
                  flex: 1,
                }}>{formatContent(e.content)}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Advisory tab ── */}
      {tab === 'advisory' && (
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px 14px',
        }}>
          <Advisory advisory={advisory} />
        </div>
      )}
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_TYPES, SEVERITY_LEVELS, DISASTER_COLOR_MAP } from './constants.js'
import { setDrawColor, clearDrawPolygon } from './Map.jsx'

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
}

const AGENT_COLORS = {
  AGENT_1: '#7B68EE',
  AGENT_2: null,
  AGENT_3: '#00FF88',
  ORCHESTRATOR: '#4A5568',
}

const MAX_ENTRIES = 150
const BACKOFF = [1000, 2000, 4000, 8000, 30000]

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
        color: '#7A8FA8',
      }}>{children}</span>
      {right && <span style={{ fontSize: 9, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{right}</span>}
    </div>
  )
}

// ─── sub-component: advisory block ──────────────────────────────────────────

function Advisory({ advisory }) {
  if (!advisory) return (
    <div style={{
      padding: '10px 0',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: '#4A6A8A',
      letterSpacing: '0.06em',
      display: 'flex',
      alignItems: 'center',
      gap: 6,
    }}>
      <span style={{ color: '#4A6A8A' }}>▮</span>
      AWAITING AGENT 3 REPORT
    </div>
  )

  const text = typeof advisory.text === 'string' ? advisory.text : null
  const structured = typeof advisory.text === 'object' ? advisory.text : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {advisory.timestamp && (
        <div style={{ fontSize: 9, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {new Date(advisory.timestamp).toLocaleTimeString()}
        </div>
      )}

      {text && (
        <p style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-primary)',
          lineHeight: 1.7,
          whiteSpace: 'pre-wrap',
        }}>{text}</p>
      )}

      {structured && (
        <>
          {structured.situation_summary && (
            <AdvisoryBlock label="Situation" color="var(--text-primary)">
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
                  {z.reason && <span style={{ color: 'var(--text-secondary)' }}> — {z.reason}</span>}
                </div>
              ))}
            </AdvisoryBlock>
          )}
          {structured.resource_requirements?.length > 0 && (
            <AdvisoryBlock label="Resources">
              {structured.resource_requirements.map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: 5 }}>
                  <span style={{ color: '#5A7A9A' }}>·</span>
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
        color: color || 'var(--text-secondary)',
        marginBottom: 4,
      }}>{label}</div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-primary)',
        lineHeight: 1.65,
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
}) {
  // ── Command state ──
  const [coords, setCoords] = useState(null)
  const [selectedType, setSelectedType] = useState(null)
  const [selectedSeverity, setSelectedSeverity] = useState(null)
  const [deployStatus, setDeployStatus] = useState('idle')

  // ── Agent feed state ──
  const [entries, setEntries] = useState([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const timerRef = useRef(null)
  const feedRef = useRef(null)

  // ── Tab state ──
  const [tab, setTab] = useState('pipeline') // 'pipeline' | 'advisory'

  // ── Sync captured coords ──
  useEffect(() => { if (capturedCoords) setCoords(capturedCoords) }, [capturedCoords])

  // ── Sync circle colour ──
  useEffect(() => { if (selectedType) setDrawColor(DISASTER_COLORS[selectedType]) }, [selectedType])

  // ── WebSocket ──
  const addEntry = useCallback((entry) => {
    setEntries((prev) => {
      const next = [entry, ...prev]
      return next.length > MAX_ENTRIES ? next.slice(0, MAX_ENTRIES) : next
    })
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(`ws://${window.location.host}/ws`)
    wsRef.current = ws

    ws.onopen = () => { setConnected(true); retryRef.current = 0 }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type !== 'agent_stream') return
        const d = msg.data || {}
        const rawId = (d.agent_id || '').toLowerCase()
        let agent = 'ORCHESTRATOR'
        if (rawId.startsWith('agent-1')) agent = 'AGENT_1'
        else if (rawId.startsWith('agent-2')) agent = 'AGENT_2'
        else if (rawId.startsWith('agent-3')) agent = 'AGENT_3'
        else if (rawId === 'world') agent = 'ORCHESTRATOR'
        else if (rawId.includes('orchestrator')) agent = 'ORCHESTRATOR'
        const content = typeof d.content === 'string' ? d.content : JSON.stringify(d.content)
        addEntry({
          id: `${Date.now()}-${Math.random()}`,
          agent,
          event: d.event || '',
          content,
          ts: new Date().toTimeString().slice(0, 8),
        })
        if ((agent === 'AGENT_3' && d.event === 'advisory_issued') || d.event === 'advisory_updated') {
          const advisoryContent = typeof d.content === 'object' ? d.content : content
          if (onAdvisoryUpdate) onAdvisoryUpdate(advisoryContent, new Date().toISOString())
          setTab('advisory')
        }
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      const delay = BACKOFF[Math.min(retryRef.current, BACKOFF.length - 1)]
      retryRef.current += 1
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [addEntry, onAdvisoryUpdate])

  useEffect(() => {
    connect()
    return () => { clearTimeout(timerRef.current); wsRef.current?.close() }
  }, [connect])

  // ── Deploy ──
  const hasZone = coords?.radius_m > 0
  const canDeploy = coords && selectedType && selectedSeverity && deployStatus === 'idle'
  const accent = selectedType ? DISASTER_COLORS[selectedType] : 'var(--text-secondary)'

  function handleClear() { clearDrawPolygon(); setCoords(null) }

  async function deploy() {
    if (!canDeploy) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setDeployStatus('failed')
      setTimeout(() => setDeployStatus('idle'), 3000)
      return
    }
    setDeployStatus('dispatching')
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
        },
      }))
      setDeployStatus('active')
      setTimeout(() => setDeployStatus('idle'), 4000)
    } catch {
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
        }}>Incident Command</span>
        <span style={{
          fontSize: 9,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.06em',
          color: connected ? 'var(--success)' : '#2A3545',
        }}>
          {connected ? '● LIVE' : '○ OFFLINE'}
        </span>
      </div>

      {/* ── Command controls ── */}
      <div style={{
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
              color: isSelectingLocation ? accent : 'var(--text-secondary)',
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
              background: '#0A0E14',
              border: `1px solid ${hasZone ? accent : 'var(--border)'}`,
              borderRadius: 3,
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--text-primary)',
              letterSpacing: '0.04em',
              lineHeight: 1.9,
            }}>
              <span style={{ color: 'var(--text-secondary)' }}>LAT  </span>{coords.lat.toFixed(5)}
              {'  '}
              <span style={{ color: 'var(--text-secondary)' }}>LON  </span>{coords.lon.toFixed(5)}
              {hasZone && (<><br />
                <span style={{ color: 'var(--text-secondary)' }}>RAD  </span>
                {coords.radius_m >= 1000 ? (coords.radius_m / 1000).toFixed(2) + ' km' : coords.radius_m + ' m'}
              </>)}
            </div>
          )}

          {isSelectingLocation && !coords && (
            <div style={{ marginTop: 5, fontSize: 10, color: '#2A3545', fontFamily: 'var(--font-mono)' }}>
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
                  background: selectedType === key ? `${color}22` : `${color}08`,
                  border: `1px solid ${selectedType === key ? color : `${color}44`}`,
                  borderRadius: 2,
                  color: selectedType === key ? color : `${color}88`,
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
                  background: active ? `${c}22` : `${c}08`,
                  border: `1px solid ${active ? c : `${c}44`}`,
                  borderRadius: 2,
                  color: active ? c : `${c}88`,
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
            color: canDeploy ? '#0A0E14' : '#4A6A8A',
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
      </div>

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
          {!connected && entries.length === 0 && (
            <div style={{
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: '#4A6A8A',
              letterSpacing: '0.05em',
            }}>○  AWAITING BACKEND</div>
          )}
          {connected && entries.length === 0 && (
            <div style={{
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: '#4A6A8A',
              display: 'flex',
              gap: 6,
            }}>
              AWAITING INCIDENT TRIGGER
              <span style={{ animation: 'blink-cursor 1s step-end infinite' }}>▮</span>
            </div>
          )}

          {entries.map((e) => {
            const agentColor = e.agent === 'AGENT_2' && activeIncidentType
              ? DISASTER_COLOR_MAP[activeIncidentType] || '#FFB800'
              : AGENT_COLORS[e.agent] || null
            return (
              <div key={e.id} style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 8,
                padding: '5px 14px',
                borderLeft: `2px solid ${agentColor || 'transparent'}`,
                borderBottom: '1px solid rgba(255,255,255,0.025)',
              }}>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-mono)',
                  color: '#4A6A8A',
                  flexShrink: 0,
                  letterSpacing: '0.02em',
                }}>{e.ts}</span>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-display)',
                  letterSpacing: '0.1em',
                  color: agentColor || '#5A7A9A',
                  fontWeight: 600,
                  flexShrink: 0,
                  minWidth: 28,
                }}>{AGENT_LABELS[e.agent] || e.agent}</span>
                {e.event && (
                  <span style={{
                    fontSize: 9,
                    fontFamily: 'var(--font-display)',
                    letterSpacing: '0.08em',
                    color: '#4A6A8A',
                    flexShrink: 0,
                  }}>{e.event}</span>
                )}
                <span style={{
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                  lineHeight: 1.5,
                  wordBreak: 'break-word',
                }}>{e.content}</span>
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

import { useState, useEffect, useRef } from 'react'
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

// ─── Orchestrator state derivation ──────────────────────────────────────────

const ORCH_STATE_COLORS = {
  STANDBY:            '#4A6A8A',
  SURVEILLANCE_ACTIVE:'#7B68EE',
  SWARM_ACTIVE:       '#FFB800',
  ADVISORY_ACTIVE:    '#00FF88',
  MULTI_INCIDENT:     '#FF8C42',
  EMERGENCY:          '#FF3B3B',
}

/**
 * Derive orchestrator state from entries (newest-first).
 * Pure function — no side effects.
 * @param {Array} entries
 * @returns {string} OrchestratorState
 */
function deriveOrchestratorState(entries) {
  if (!entries.length) return 'STANDBY'
  for (const e of entries) {
    const c = (e.content || '').toUpperCase()
    const agent = e.agent || ''
    if (c.includes('EMERGENCY')) return 'EMERGENCY'
    if (agent === 'ORCHESTRATOR' && c.includes('SWARM_ACTIVE')) return 'SWARM_ACTIVE'
    if (agent === 'ORCHESTRATOR' && c.includes('SURVEILLANCE_ACTIVE')) return 'SURVEILLANCE_ACTIVE'
    if (agent === 'AGENT_3' && e.event === 'advisory_issued') return 'ADVISORY_ACTIVE'
    if (agent === 'AGENT_3' && c.includes('ADVISORY')) return 'ADVISORY_ACTIVE'
  }
  return 'STANDBY'
}

/**
 * Derive active agent from entries (newest-first).
 * Pure function — O(1).
 * @param {Array} entries
 * @returns {string|null}
 */
function deriveActiveAgent(entries) {
  return entries.length ? entries[0].agent : null
}

// ─── OrchestratorHUD sub-component ──────────────────────────────────────────

function OrchestratorHUD({ orchestratorState, activeAgent }) {
  const stateColor = ORCH_STATE_COLORS[orchestratorState] || ORCH_STATE_COLORS.STANDBY

  const agents = [
    { id: 'AGENT_1', label: 'A1', color: AGENT_COLORS.AGENT_1 || '#7B68EE' },
    { id: 'AGENT_2', label: 'A2', color: '#FFB800' },
    { id: 'AGENT_3', label: 'A3', color: AGENT_COLORS.AGENT_3 || '#00FF88' },
  ]

  return (
    <div style={{
      padding: '8px 14px',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      gap: 7,
      flexShrink: 0,
    }}>
      {/* State badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 9,
          fontFamily: 'var(--font-display)',
          letterSpacing: '0.1em',
          color: '#4A6A8A',
        }}>ORCHESTRATOR</span>
        <span style={{
          fontSize: 9,
          fontFamily: 'var(--font-display)',
          letterSpacing: '0.1em',
          fontWeight: 700,
          color: stateColor,
          padding: '2px 6px',
          border: `1px solid ${stateColor}`,
          borderRadius: 2,
          boxShadow: `0 0 6px ${stateColor}44`,
          transition: 'color 0.15s, border-color 0.15s, box-shadow 0.15s',
        }}>
          {orchestratorState}
        </span>
      </div>

      {/* Agent pipeline flow: A1 ──▶ A2 ──▶ A3 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {agents.map((a, i) => {
          const isActive = activeAgent === a.id
          return (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                padding: '3px 8px',
                border: `1px solid ${isActive ? a.color : `${a.color}44`}`,
                borderRadius: 2,
                fontFamily: 'var(--font-display)',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.1em',
                color: isActive ? a.color : `${a.color}66`,
                opacity: isActive ? 1 : 0.35,
                boxShadow: isActive ? `0 0 8px ${a.color}55` : 'none',
                transition: 'all 0.15s',
              }}>
                {a.label}
              </div>
              {i < agents.length - 1 && (
                <span style={{ color: '#2A3545', fontSize: 10, userSelect: 'none' }}>──▶</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

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
  if (!advisory || (!advisory.text && !advisory.sections)) return (
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

  const s = advisory.sections || null

  const splitLines = (str) =>
    (str || '').split('\n').map((l) => l.trim()).filter(Boolean)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {advisory.timestamp && (
        <div style={{ fontSize: 9, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
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
          fontSize: 11,
          color: 'var(--text-primary)',
          lineHeight: 1.7,
          whiteSpace: 'pre-wrap',
        }}>{advisory.text || ''}</p>
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
  agentEntries,
  wsConnected,
  onSend,
}) {
  // ── Command state ──
  const [coords, setCoords] = useState(null)
  const [selectedType, setSelectedType] = useState(null)
  const [selectedSeverity, setSelectedSeverity] = useState(null)
  const [deployStatus, setDeployStatus] = useState('idle')

  const entries = agentEntries || []
  const feedRef = useRef(null)

  // ── Tab state ──
  const [tab, setTab] = useState('pipeline') // 'pipeline' | 'advisory'

  // ── Sync captured coords ──
  useEffect(() => { if (capturedCoords) setCoords(capturedCoords) }, [capturedCoords])

  // ── Sync circle colour ──
  useEffect(() => { if (selectedType) setDrawColor(DISASTER_COLORS[selectedType]) }, [selectedType])

  // ── Auto-switch to advisory tab when a new advisory arrives ──
  useEffect(() => { if (advisory) setTab('advisory') }, [advisory])

  // ── Deploy ──
  const hasZone = coords?.radius_m > 0
  const canDeploy = coords && selectedType && selectedSeverity && deployStatus === 'idle'
  const accent = selectedType ? DISASTER_COLORS[selectedType] : 'var(--text-secondary)'

  function handleClear() { clearDrawPolygon(); setCoords(null) }

  function deploy() {
    if (!canDeploy) return
    if (!wsConnected) {
      setDeployStatus('failed')
      setTimeout(() => setDeployStatus('idle'), 3000)
      return
    }
    setDeployStatus('dispatching')
    onSend({
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
    })
    setDeployStatus('active')
    setTimeout(() => setDeployStatus('idle'), 4000)
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
          color: wsConnected ? 'var(--success)' : '#2A3545',
        }}>
          {wsConnected ? '● LIVE' : '○ OFFLINE'}
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
            color: canDeploy ? '#FFFFFF' : '#4A6A8A',
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
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <OrchestratorHUD
            orchestratorState={deriveOrchestratorState(entries)}
            activeAgent={deriveActiveAgent(entries)}
          />
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
            {!wsConnected && entries.length === 0 && (
              <div style={{
                padding: '14px',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: '#4A6A8A',
                letterSpacing: '0.05em',
              }}>○  AWAITING BACKEND</div>
            )}
            {wsConnected && entries.length === 0 && (
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
              const displayContent = e.content.length > 120
                ? e.content.slice(0, 120) + '…'
                : e.content
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
                  }}>{displayContent}</span>
                </div>
              )
            })}
          </div>
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

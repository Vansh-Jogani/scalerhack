import { useState, useEffect, useRef } from 'react'
import { DISASTER_COLOR_MAP, MAX_ZONE_RADIUS_M } from './constants.js'
import { setDrawColor, clearDrawPolygon } from './Map.jsx'

// ── Design tokens ────────────────────────────────────────────────────────────
const ACCENTS = {
  fire:                { hex: '#ff5a4d', name: 'FIRE' },
  structural_collapse: { hex: '#ff9046', name: 'STRUCTURAL' },
  flood:               { hex: '#5aa8ff', name: 'FLOOD' },
  industrial_hazard:   { hex: '#d4d4aa', name: 'INDUSTRIAL' },
  maritime_sar:        { hex: '#5ee0d0', name: 'MARITIME SAR' },
}

const A1_COLOR = '#9C8AFF'
const A3_COLOR = '#5ee08b'
const SEV_LABELS = ['LOW', 'MED', 'HIGH', 'CRIT']
const SEV_COLORS = ['#6EE7B7', '#FCD34D', '#F97316', '#EF4444']
const DISASTER_KEYS = Object.keys(ACCENTS)

// ── Atoms ────────────────────────────────────────────────────────────────────
function Dot({ color = '#5ee08b', size = 6, pulse = false }) {
  return (
    <span style={{ position: 'relative', display: 'inline-block', width: size, height: size, flexShrink: 0 }}>
      <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: color, boxShadow: `0 0 ${size * 1.6}px ${color}` }} />
      {pulse && <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `1px solid ${color}`, animation: 'ringPulse 1.8s ease-out infinite' }} />}
    </span>
  )
}

function Lbl({ children, color = 'rgba(232,237,245,0.42)', size = 11, tracking = '0.14em' }) {
  return <div style={{ fontFamily: 'var(--font-display)', fontSize: size, fontWeight: 600, letterSpacing: tracking, textTransform: 'uppercase', color }}>{children}</div>
}

function Mn({ children, color = 'rgba(232,237,245,0.78)', size = 12, weight = 400, style: s }) {
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: size, color, fontWeight: weight, letterSpacing: '0.02em', ...s }}>{children}</span>
}

// ── Glass surface ─────────────────────────────────────────────────────────────
function Glass({ children, style = {}, radius = 20 }) {
  return (
    <div style={{
      position: 'relative', borderRadius: radius,
      background: 'rgba(10, 14, 20, 0.58)',
      backdropFilter: 'blur(32px) saturate(155%)',
      WebkitBackdropFilter: 'blur(32px) saturate(155%)',
      border: '1px solid rgba(255,255,255,0.07)',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), inset 0 0 0 1px rgba(255,255,255,0.01), 0 32px 64px rgba(0,0,0,0.55), 0 12px 24px rgba(0,0,0,0.35)',
      overflow: 'hidden', ...style,
    }}>
      <div style={{ position: 'absolute', top: 0, left: 16, right: 16, height: 1, background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)', pointerEvents: 'none' }} />
      {children}
    </div>
  )
}

// ── Identity pill (always shown) ──────────────────────────────────────────────
function IdentityPill({ wsConnected, systemStatus, missionActive, incidentId }) {
  const [tick, setTick] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTick(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const timeStr = tick.toISOString().slice(11, 19) + 'Z'
  return (
    <Glass radius={999} style={{ padding: '10px 18px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Dot color="#5ee08b" size={6} pulse={wsConnected} />
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, letterSpacing: '0.32em', color: '#F4F7FB' }}>ARIA</span>
          <span style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.12)' }} />
          <Mn color="rgba(232,237,245,0.5)" size={9}>{missionActive ? systemStatus : 'STANDBY'}</Mn>
        </div>
        <Mn color="rgba(232,237,245,0.4)" size={9}>{timeStr}</Mn>
      </div>
    </Glass>
  )
}

// ── Mission card (active) ─────────────────────────────────────────────────────
function MissionCard({ accent, severity, incidentId, coords, deployedAt, droneCount, swarmCount }) {
  const c = accent.hex
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!deployedAt) return
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - deployedAt) / 1000)), 1000)
    return () => clearInterval(id)
  }, [deployedAt])
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')
  return (
    <Glass radius={20} style={{ flexShrink: 0 }}>
      <div style={{ padding: '14px 18px', background: `radial-gradient(circle at top right, ${c}12, transparent 60%)` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <Lbl color={c}>Mission · Active</Lbl>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: '#F4F7FB', marginTop: 3, letterSpacing: '0.04em' }}>
              {accent.name} · <span style={{ color: 'rgba(232,237,245,0.65)' }}>{SEV_LABELS[severity]}</span>
            </div>
            {coords && <Mn color="rgba(232,237,245,0.48)" size={9.5} style={{ marginTop: 4 }}>{coords.lat.toFixed(4)}° N · {coords.lon.toFixed(4)}° E</Mn>}
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 500, color: c, fontVariantNumeric: 'tabular-nums', letterSpacing: '0.04em' }}>{mm}:{ss}</div>
            <Mn color="rgba(232,237,245,0.4)" size={8.5}>ELAPSED</Mn>
          </div>
        </div>
        {/* flowing progress bar */}
        <div style={{ marginTop: 12, position: 'relative', height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, width: '70%', background: `linear-gradient(90deg, transparent, ${c}88 30%, ${c} 50%, ${c}88 70%, transparent)`, backgroundSize: '200% 100%', animation: 'flow 2.4s linear infinite', borderRadius: 2 }} />
        </div>
        <div style={{ marginTop: 10, display: 'flex', gap: 16 }}>
          <InlineStat label="AIRCRAFT" val={String(droneCount)} />
          <InlineStat label="SWARM" val={String(swarmCount)} />
          <InlineStat label="ZONE" val={coords?.radius_m ? `${coords.radius_m}m` : '—'} />
          {incidentId && <InlineStat label="INC" val={incidentId.slice(-8)} color={`${c}cc`} />}
        </div>
      </div>
    </Glass>
  )
}

function InlineStat({ label, val, color = '#F4F7FB' }) {
  return (
    <div>
      <Mn color="rgba(232,237,245,0.35)" size={8} weight={500}>{label}</Mn>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color, marginTop: 1, fontVariantNumeric: 'tabular-nums' }}>{val}</div>
    </div>
  )
}

// ── Agent row (active) ────────────────────────────────────────────────────────
function AgentCard({ agentStates, accent }) {
  const c = accent.hex
  const agents = [
    { num: 'A1', name: 'Surveillance',  color: A1_COLOR, key: 'A1', stateMap: { idle: 'STANDBY', active: 'SCANNING', done: 'LOITERING', error: 'ERROR' } },
    { num: 'A2', name: 'Specialist Swarm', color: c,     key: 'A2', stateMap: { idle: 'STANDBY', active: 'DEPLOYED', done: 'COMPLETE', error: 'ERROR' } },
    { num: 'A3', name: 'Advisory',      color: A3_COLOR, key: 'A3', stateMap: { idle: 'STANDBY', active: 'GENERATING', done: 'ISSUED', error: 'ERROR' } },
  ]
  return (
    <Glass radius={20} style={{ flexShrink: 0 }}>
      <div style={{ padding: '14px 18px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
          <Lbl>Agents</Lbl>
          <Mn color="rgba(232,237,245,0.4)" size={9}>LANGGRAPH · 3 NODES</Mn>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {agents.map((a) => {
            const state = agentStates[a.key] || 'idle'
            const stateLabel = a.stateMap[state] || 'STANDBY'
            const isActive = state === 'active'
            const isDone = state === 'done'
            const stateColor = state === 'error' ? '#EF4444' : isDone ? '#5ee08b' : isActive ? a.color : 'rgba(232,237,245,0.3)'
            return (
              <div key={a.num} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: `linear-gradient(90deg, ${a.color}10, transparent 70%)`, border: `1px solid ${state === 'idle' ? 'rgba(255,255,255,0.06)' : a.color + '22'}`, borderRadius: 12 }}>
                <div style={{ width: 30, height: 30, borderRadius: 10, background: 'rgba(10,14,20,0.6)', border: `1px solid ${a.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', flexShrink: 0 }}>
                  <Mn color={a.color} size={10} weight={700}>{a.num}</Mn>
                  <span style={{ position: 'absolute', bottom: -1, right: -1, width: 7, height: 7, borderRadius: '50%', background: stateColor, boxShadow: isActive ? `0 0 8px ${a.color}` : 'none', border: '1.5px solid rgba(10,14,20,0.9)', animation: isActive ? 'breathe 2s ease-in-out infinite' : 'none' }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600, color: '#F4F7FB', letterSpacing: '0.06em' }}>{a.name}</span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 500, color: stateColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{stateLabel}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </Glass>
  )
}

// ── Stream feed (active) ──────────────────────────────────────────────────────
function StreamCard({ feedEntries, accent, advisory }) {
  const c = accent.hex
  const [tab, setTab] = useState('feed')
  useEffect(() => { if (advisory) setTab('advisory') }, [advisory])
  const agentColors = { A1: A1_COLOR, A2: c, A3: A3_COLOR, SYS: 'rgba(232,237,245,0.42)' }
  return (
    <Glass radius={20} style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '12px 18px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 0 }}>
          {[['feed', 'Stream'], ['advisory', 'Advisory']].map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)} style={{ padding: '0 0 10px', marginRight: 18, background: 'transparent', border: 'none', borderBottom: `2px solid ${tab === id ? c : 'transparent'}`, color: tab === id ? '#F4F7FB' : 'rgba(232,237,245,0.4)', fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', cursor: 'pointer' }}>
              {label}
              {id === 'advisory' && advisory && <span style={{ marginLeft: 4, color: '#5ee08b' }}>●</span>}
            </button>
          ))}
        </div>
        {tab === 'feed' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, paddingBottom: 10 }}>
            <Dot color={c} size={4} pulse={feedEntries.length > 0} />
            <Mn color={c} size={9} weight={600}>LIVE</Mn>
          </div>
        )}
      </div>
      <div style={{ height: 1, margin: '0 18px', background: 'rgba(255,255,255,0.05)' }} />

      {tab === 'feed' && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0 14px', display: 'flex', flexDirection: 'column-reverse' }}>
          {feedEntries.length === 0 && (
            <div style={{ padding: '14px 18px', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(232,237,245,0.28)', letterSpacing: '0.04em' }}>
              ⟳  Agents initialising…
            </div>
          )}
          {feedEntries.map((e) => {
            const fc = agentColors[e.agent] || '#7A8FA8'
            return (
              <div key={e.id} style={{ display: 'flex', gap: 8, padding: '6px 18px', borderBottom: '1px solid rgba(255,255,255,0.03)', alignItems: 'flex-start', animation: 'ticker 0.2s ease-out' }}>
                <Mn color="rgba(232,237,245,0.28)" size={10} weight={500}>{e.ts}</Mn>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, color: fc, letterSpacing: '0.06em', minWidth: 22, flexShrink: 0 }}>{e.agent}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {e.event && <div style={{ fontSize: 9, color: 'rgba(232,237,245,0.38)', textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', fontWeight: 600, marginBottom: 1 }}>{e.event}</div>}
                  <div style={{ fontSize: 12, color: 'rgba(232,237,245,0.8)', lineHeight: 1.45, fontFamily: 'var(--font-mono)', wordBreak: 'break-word' }}>{e.content}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {tab === 'advisory' && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px 14px' }}>
          {!advisory ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(232,237,245,0.28)' }}>▮ Awaiting Agent 3 advisory</div>
          ) : <Advisory advisory={advisory} c={c} />}
        </div>
      )}
    </Glass>
  )
}

function Advisory({ advisory, c }) {
  const s = advisory?.data
  if (!s) return null
  const block = (label, color, children) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: color || 'rgba(232,237,245,0.5)', marginBottom: 7 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'rgba(232,237,245,0.82)', lineHeight: 1.65 }}>{children}</div>
    </div>
  )
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(232,237,245,0.32)', marginBottom: 14 }}>{new Date(advisory.ts).toLocaleTimeString()}</div>
      {s.situation_summary && block('Situation', '#F4F7FB', s.situation_summary)}
      {s.immediate_actions?.length > 0 && block('Immediate Actions', '#5ee08b',
        s.immediate_actions.map((a, i) => <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 6 }}><span style={{ color: '#5ee08b', flexShrink: 0, fontWeight: 700 }}>{String(i + 1).padStart(2, '0')}</span><span>{a}</span></div>)
      )}
      {s.risk_flags?.length > 0 && block('Risk Flags', '#FCD34D',
        s.risk_flags.map((f, i) => <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 4 }}><span style={{ color: '#FCD34D', flexShrink: 0 }}>⚠</span><span>{f}</span></div>)
      )}
      {s.exclusion_zones?.length > 0 && block('Exclusion Zones', '#EF4444',
        s.exclusion_zones.map((z, i) => <div key={i} style={{ marginBottom: 4 }}><span style={{ color: '#EF4444', fontWeight: 600 }}>{z.radius_m}m</span><span style={{ color: 'rgba(232,237,245,0.5)' }}> @ {z.lat?.toFixed(4)}, {z.lon?.toFixed(4)}</span>{z.reason && <div style={{ color: 'rgba(232,237,245,0.55)', fontSize: 12, marginTop: 1 }}>{z.reason}</div>}</div>)
      )}
      {s.resource_requirements?.length > 0 && block('Resources', '#5aa8ff',
        s.resource_requirements.map((r, i) => <div key={i} style={{ marginBottom: 3 }}><span style={{ color: '#5aa8ff' }}>· </span>{r}</div>)
      )}
      {s.monitoring_status && block('Monitoring', 'rgba(232,237,245,0.6)', s.monitoring_status)}
    </div>
  )
}

// ── Setup cards ───────────────────────────────────────────────────────────────
function SetupView({ type, severity, setSeverity, setType, capturedCoords, setCapturedCoords, isSelectingLocation, onStartSelect, onDeploy, deploying }) {
  const accent = ACCENTS[type] || ACCENTS.fire
  const c = type ? accent.hex : 'rgba(232,237,245,0.4)'
  const ready = !!capturedCoords && !!type && severity !== null && !deploying

  useEffect(() => { if (type) setDrawColor(ACCENTS[type]?.hex || '#ff5a4d') }, [type])

  return (
    <>
      {/* Hero prompt */}
      <Glass radius={20} style={{ flexShrink: 0 }}>
        <div style={{ padding: '20px 18px 16px' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: '#F4F7FB', lineHeight: 1.1, fontStyle: 'italic' }}>Mark a zone.</div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'rgba(232,237,245,0.38)', lineHeight: 1.1, fontStyle: 'italic' }}>Dispatch a swarm.</div>
          <div style={{ fontSize: 12, color: 'rgba(232,237,245,0.5)', marginTop: 10, lineHeight: 1.55 }}>ARIA classifies the incident, selects the right specialist swarm, and issues a response plan in under 90 seconds.</div>
        </div>
      </Glass>

      {/* Zone card */}
      <Glass radius={20} style={{ flexShrink: 0 }}>
        <div style={{ padding: '14px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
            <Lbl>Zone</Lbl><Mn color="rgba(232,237,245,0.34)" size={9}>01</Mn>
          </div>
          {capturedCoords ? (
            <div style={{ padding: '8px 12px', background: `${c}10`, border: `1px solid ${c}33`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Mn color="#F4F7FB" size={11}>{capturedCoords.lat.toFixed(4)}° N · {capturedCoords.lon.toFixed(4)}° E · r={capturedCoords.radius_m}m</Mn>
              <button onClick={() => { clearDrawPolygon(); setCapturedCoords(null) }} style={{ background: 'transparent', border: 'none', color: 'rgba(232,237,245,0.45)', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 13, padding: '0 0 0 10px' }}>✕</button>
            </div>
          ) : (
            <button onClick={onStartSelect} style={{ width: '100%', padding: '12px 14px', background: isSelectingLocation ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.03)', border: `1px ${isSelectingLocation ? 'solid rgba(255,255,255,0.2)' : 'dashed rgba(255,255,255,0.16)'}`, borderRadius: 10, color: isSelectingLocation ? '#F4F7FB' : 'rgba(232,237,245,0.65)', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.04em', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{isSelectingLocation ? '◎  Click centre → click edge for radius' : 'Tap map to mark centre'}</span>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: '#5aa8ff', letterSpacing: '0.1em' }}>↗</span>
            </button>
          )}
        </div>
      </Glass>

      {/* Classify card */}
      <Glass radius={20} style={{ flexShrink: 0 }}>
        <div style={{ padding: '14px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
            <Lbl>Classify</Lbl><Mn color="rgba(232,237,245,0.34)" size={9}>02</Mn>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {DISASTER_KEYS.map((key) => {
              const a = ACCENTS[key]
              const active = type === key
              return (
                <button key={key} onClick={() => setType(key)} style={{ padding: '6px 12px', background: active ? `${a.hex}1f` : 'rgba(255,255,255,0.03)', border: `1px solid ${active ? a.hex + '66' : 'rgba(255,255,255,0.08)'}`, borderRadius: 999, color: active ? a.hex : 'rgba(232,237,245,0.6)', fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, boxShadow: active ? `0 0 12px ${a.hex}22` : 'none' }}>
                  <span style={{ width: 5, height: 5, borderRadius: '50%', background: active ? a.hex : 'rgba(232,237,245,0.32)', boxShadow: active ? `0 0 6px ${a.hex}` : 'none' }} />
                  {a.name}
                </button>
              )
            })}
          </div>
        </div>
      </Glass>

      {/* Severity card */}
      <Glass radius={20} style={{ flexShrink: 0 }}>
        <div style={{ padding: '14px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
            <Lbl>Severity</Lbl><Mn color="rgba(232,237,245,0.34)" size={9}>03</Mn>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 5 }}>
            {SEV_LABELS.map((l, i) => {
              const sc = SEV_COLORS[i]
              const active = severity === i
              return (
                <button key={l} onClick={() => setSeverity(i)} style={{ padding: '8px 0', background: active ? sc + '1f' : 'rgba(255,255,255,0.03)', border: `1px solid ${active ? sc + '66' : 'rgba(255,255,255,0.08)'}`, borderRadius: 10, cursor: 'pointer', color: active ? sc : 'rgba(232,237,245,0.55)', fontFamily: 'var(--font-display)', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', transition: 'all 0.1s' }}>{l}</button>
              )
            })}
          </div>
        </div>
      </Glass>

      <div style={{ flex: 1 }} />

      {/* Deploy pill */}
      <Glass radius={999} style={{ flexShrink: 0, padding: 0, overflow: 'hidden' }}>
        <button onClick={onDeploy} disabled={!ready} style={{ width: '100%', padding: '15px', background: ready ? `linear-gradient(180deg, ${c}, ${c}cc)` : 'rgba(255,255,255,0.025)', border: 'none', borderRadius: 999, color: ready ? '#0a0d12' : 'rgba(232,237,245,0.35)', cursor: ready ? 'pointer' : 'not-allowed', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', boxShadow: ready ? `0 0 32px ${c}55, inset 0 1px 0 rgba(255,255,255,0.3)` : 'none', transition: 'all 0.15s' }}>
          {deploying ? '⟳  DEPLOYING…' : 'Deploy Mission ↗'}
        </button>
      </Glass>
    </>
  )
}

// ── Root panel ────────────────────────────────────────────────────────────────
export default function SidePanel({ wsConnected, systemStatus, isSelectingLocation, onStartSelect, capturedCoords, setCapturedCoords, agentStates, feedEntries, advisory, onMissionStart }) {
  const [type, setType] = useState(null)
  const [severity, setSeverity] = useState(null)
  const [deploying, setDeploying] = useState(false)
  const [missionActive, setMissionActive] = useState(false)
  const [deployedAt, setDeployedAt] = useState(null)
  const [incidentId, setIncidentId] = useState(null)
  const [droneCount, setDroneCount] = useState(1)
  const [swarmCount, setSwarmCount] = useState(0)

  const accent = ACCENTS[type] || ACCENTS.fire

  // Count drones from agentStates changes
  useEffect(() => {
    if (agentStates.A2 === 'active' || agentStates.A2 === 'done') setSwarmCount(3)
  }, [agentStates.A2])

  async function deploy() {
    if (!capturedCoords || !type || severity === null || deploying) return
    setDeploying(true)
    try {
      const res = await fetch('/api/incident/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: capturedCoords.lat, lon: capturedCoords.lon,
          zone_radius_m: capturedCoords.radius_m || 300,
          disaster_type: type, severity: SEV_LABELS[severity].toLowerCase(),
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setMissionActive(true)
        setDeployedAt(Date.now())
        setIncidentId(data.incident_id || null)
        onMissionStart?.()
      }
    } catch (e) { console.error('deploy failed', e) }
    finally { setDeploying(false) }
  }

  function reset() {
    clearDrawPolygon()
    setCapturedCoords(null)
    setMissionActive(false)
    setDeployedAt(null)
    setIncidentId(null)
    setType(null)
    setSeverity(null)
    setSwarmCount(0)
    setDroneCount(1)
  }

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, bottom: 0, width: 320,
      display: 'flex', flexDirection: 'column', gap: 10,
      padding: '20px 16px', zIndex: 10, overflowY: 'auto',
    }}>
      <IdentityPill wsConnected={wsConnected} systemStatus={systemStatus} missionActive={missionActive} incidentId={incidentId} />

      {!missionActive && (
        <SetupView
          type={type} severity={severity} setSeverity={setSeverity} setType={setType}
          capturedCoords={capturedCoords} setCapturedCoords={setCapturedCoords}
          isSelectingLocation={isSelectingLocation} onStartSelect={onStartSelect}
          onDeploy={deploy} deploying={deploying}
        />
      )}

      {missionActive && (
        <>
          <MissionCard
            accent={accent} severity={severity ?? 0} incidentId={incidentId}
            coords={capturedCoords} deployedAt={deployedAt}
            droneCount={droneCount} swarmCount={swarmCount}
          />
          <AgentCard agentStates={agentStates} accent={accent} />
          <StreamCard feedEntries={feedEntries} accent={accent} advisory={advisory} />
          <Glass radius={999} style={{ flexShrink: 0, padding: 0 }}>
            <button onClick={reset} style={{ width: '100%', padding: '10px', background: 'transparent', border: 'none', color: 'rgba(232,237,245,0.5)', fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600, letterSpacing: '0.16em', cursor: 'pointer' }}>RESET MISSION</button>
          </Glass>
        </>
      )}
    </div>
  )
}

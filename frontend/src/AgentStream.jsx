import { useEffect, useRef } from 'react'

const AGENT_COLORS = {
  'agent-1': '#00e5ff',
  'agent-2': '#ff9800',
  'agent-3': '#66bb6a',
  'world': '#ef5350',
}

const PANEL = {
  position: 'absolute',
  top: 0,
  right: 0,
  width: '280px',
  height: '50%',
  background: 'rgba(10,10,18,0.88)',
  borderLeft: '1px solid rgba(255,255,255,0.08)',
  borderBottom: '1px solid rgba(255,255,255,0.08)',
  display: 'flex',
  flexDirection: 'column',
  fontFamily: 'monospace',
  fontSize: '11px',
  zIndex: 10,
}

function eventLabel(event) {
  const map = {
    started: 'STARTED',
    survey_started: 'SURVEY',
    sensor_hit: 'SENSOR HIT',
    classified: 'CLASSIFIED',
    swarm_deployed: 'SWARM DEPLOYED',
    findings_reported: 'FINDINGS',
    advisory_issued: 'ADVISORY',
    world_event: 'WORLD EVENT',
    tool_call: 'TOOL',
  }
  return map[event] || event.toUpperCase()
}

function formatContent(content) {
  if (!content) return ''
  if (typeof content === 'string') return content.slice(0, 80)
  try {
    return JSON.stringify(content).slice(0, 80)
  } catch {
    return String(content).slice(0, 80)
  }
}

export default function AgentStream({ events }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div style={PANEL}>
      <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#aaa', letterSpacing: '0.08em', fontSize: '10px' }}>
        AGENT REASONING
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {events.length === 0 && (
          <div style={{ color: '#444', padding: '8px 10px' }}>Waiting for GO signal…</div>
        )}
        {events.slice(-30).map((e, i) => {
          const color = AGENT_COLORS[e.agent_id] || '#888'
          return (
            <div key={i} style={{ padding: '3px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color, marginRight: '6px', fontSize: '10px' }}>{e.agent_id}</span>
              <span style={{ color: '#666', marginRight: '6px' }}>{eventLabel(e.event)}</span>
              <span style={{ color: '#bbb' }}>{formatContent(e.content)}</span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { DISASTER_COLOR_MAP } from './constants.js'

const AGENT_ACCENT = {
  ORCHESTRATOR: null,
  AGENT_1: '#7B68EE',
  AGENT_2: null, // set dynamically to active incident disaster color
  AGENT_3: '#00FF88',
}

const MAX_ENTRIES = 200
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 30000]

function AgentFeed({ onAdvisoryUpdate, activeIncidentType }) {
  const [entries, setEntries] = useState([])
  const [connected, setConnected] = useState(true)
  const bottomRef = useRef(null)

  const addEntry = useCallback((entry) => {
    setEntries((prev) => {
      const next = [entry, ...prev]
      return next.length > MAX_ENTRIES ? next.slice(0, MAX_ENTRIES) : next
    })
  }, [])

  // Listen for agent events dispatched by App.jsx from main WS
  useEffect(() => {
    const handler = (e) => {
      setConnected(true)
      const entry = {
        id: `evt-${Date.now()}-${Math.random()}`,
        agent: e.detail.agent,
        timestamp: new Date().toTimeString().slice(0, 8),
        text: e.detail.text,
        incident_id: null,
      }
      addEntry(entry)

      // Extract advisory from Agent 3
      if (e.detail.agent === 'AGENT_3' && e.detail.text && onAdvisoryUpdate) {
        onAdvisoryUpdate(e.detail.text, entry.timestamp)
      }
    }
    window.addEventListener('aria-agent-event', handler)
    return () => window.removeEventListener('aria-agent-event', handler)
  }, [addEntry, onAdvisoryUpdate])

  // Auto-scroll to newest (entries are prepended, so scroll to top)
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [entries])

  function accentForAgent(agent) {
    if (agent === 'AGENT_2' && activeIncidentType) {
      return DISASTER_COLOR_MAP[activeIncidentType] || '#FFB800'
    }
    return AGENT_ACCENT[agent] || null
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--surface)' }}>
      <div className="panel-header">
        <span>AGENT PIPELINE</span>
        <span style={{
          fontSize: 10,
          fontWeight: 400,
          color: connected ? 'var(--success)' : 'var(--warning)',
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.05em',
        }}>
          {connected ? '● LIVE' : '○ CONNECTING'}
        </span>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column-reverse',
          padding: '6px 0',
          background: 'var(--surface)',
        }}
      >
        <div ref={bottomRef} />

        {!connected && entries.length === 0 && (
          <div className="connection-banner" style={{ margin: '8px 10px' }}>
            <span>○</span>
            <span>AWAITING BACKEND CONNECTION</span>
          </div>
        )}

        {connected && entries.length === 0 && (
          <div style={{
            padding: '16px 14px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}>
            AWAITING INCIDENT TRIGGER
            <span style={{ animation: 'blink-cursor 1s step-end infinite' }}>▮</span>
          </div>
        )}

        {entries.map((entry) => {
          const accent = accentForAgent(entry.agent)
          return (
            <div
              key={entry.id}
              className={`agent-entry${entry.agent === 'ORCHESTRATOR' ? ' orchestrator' : ''}`}
              style={{ borderLeftColor: accent || 'transparent' }}
            >
              <span className="entry-time">[{entry.timestamp}]</span>
              <span
                className="entry-label"
                style={{ color: accent || 'var(--text-secondary)' }}
              >
                {entry.agent}
              </span>
              <span className="entry-text">{entry.text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default AgentFeed

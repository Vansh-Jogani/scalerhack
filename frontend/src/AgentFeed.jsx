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
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef(null)
  const bottomRef = useRef(null)

  const addEntry = useCallback((entry) => {
    setEntries((prev) => {
      const next = [entry, ...prev]
      return next.length > MAX_ENTRIES ? next.slice(0, MAX_ENTRIES) : next
    })
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(`ws://${window.location.host}/ws/agents`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryCountRef.current = 0
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type !== 'agent_event') return

        addEntry({
          id: `${msg.timestamp}-${Math.random()}`,
          agent: msg.agent,
          timestamp: msg.timestamp,
          text: msg.text,
          incident_id: msg.incident_id,
        })

        // Extract advisory from Agent 3
        if (msg.agent === 'AGENT_3' && msg.text && onAdvisoryUpdate) {
          onAdvisoryUpdate(msg.text, msg.timestamp)
        }
      } catch (e) {
        console.warn('[AgentFeed] parse error', e)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      const delay = BACKOFF_STEPS[Math.min(retryCountRef.current, BACKOFF_STEPS.length - 1)]
      retryCountRef.current += 1
      retryTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [addEntry, onAdvisoryUpdate])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(retryTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  useEffect(() => {
    const handler = (e) => {
      addEntry({
        id: `local-${Date.now()}-${Math.random()}`,
        agent: e.detail.agent,
        timestamp: new Date().toTimeString().slice(0, 8),
        text: e.detail.text,
        incident_id: null,
      })
    }
    window.addEventListener('aria-agent-event', handler)
    return () => window.removeEventListener('aria-agent-event', handler)
  }, [addEntry])

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

const PANEL = {
  position: 'absolute',
  top: 0,
  left: 0,
  width: '220px',
  background: 'rgba(10,10,18,0.88)',
  borderRight: '1px solid rgba(255,255,255,0.08)',
  borderBottom: '1px solid rgba(255,255,255,0.08)',
  fontFamily: 'monospace',
  fontSize: '11px',
  zIndex: 10,
  maxHeight: '60vh',
  overflowY: 'auto',
}

const STATE_COLORS = {
  IDLE: '#555',
  FLYING: '#00e5ff',
  LOITERING: '#ffd54f',
  RTL: '#ff9800',
  THERMAL_SCAN: '#ce93d8',
}

function BatteryBar({ pct }) {
  const color = pct > 50 ? '#66bb6a' : pct > 20 ? '#ffd54f' : '#ef5350'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <div style={{ width: '36px', height: '5px', background: '#222', borderRadius: '2px' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', background: color, borderRadius: '2px', transition: 'width 0.5s' }} />
      </div>
      <span style={{ color: '#666', fontSize: '10px' }}>{Math.round(pct)}%</span>
    </div>
  )
}

export default function DroneStatus({ drones }) {
  const entries = Object.entries(drones)

  return (
    <div style={PANEL}>
      <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#aaa', letterSpacing: '0.08em', fontSize: '10px' }}>
        FLEET STATUS ({entries.length})
      </div>
      {entries.length === 0 && (
        <div style={{ color: '#333', padding: '8px 10px' }}>No drones</div>
      )}
      {entries.map(([id, d]) => {
        const stateColor = STATE_COLORS[d.state] || '#888'
        return (
          <div key={id} style={{ padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px' }}>
              <span style={{ color: '#ddd' }}>{id}</span>
              <span style={{ color: stateColor, fontSize: '10px', letterSpacing: '0.05em' }}>{d.state}</span>
            </div>
            <BatteryBar pct={d.battery_pct ?? 100} />
            <div style={{ color: '#444', marginTop: '2px', fontSize: '10px' }}>
              {d.lat?.toFixed(4)}, {d.lon?.toFixed(4)} · {Math.round(d.alt ?? 0)}m
            </div>
          </div>
        )
      })}
    </div>
  )
}

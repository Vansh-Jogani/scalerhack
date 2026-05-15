const PANEL = {
  position: 'absolute',
  bottom: 0,
  right: 0,
  width: '280px',
  height: '50%',
  background: 'rgba(10,10,18,0.92)',
  borderLeft: '1px solid rgba(255,255,255,0.08)',
  borderTop: '1px solid rgba(255,255,255,0.08)',
  display: 'flex',
  flexDirection: 'column',
  fontFamily: 'sans-serif',
  fontSize: '11px',
  zIndex: 10,
  overflowY: 'auto',
}

const SECTION = { marginBottom: '8px' }
const LABEL = { color: '#555', fontSize: '9px', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '3px' }
const BODY = { color: '#ccc', lineHeight: '1.5' }

export default function AdvisoryPanel({ advisory }) {
  return (
    <div style={PANEL}>
      <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#aaa', letterSpacing: '0.08em', fontSize: '10px', flexShrink: 0 }}>
        ADVISORY
        {advisory?.last_updated && (
          <span style={{ float: 'right', color: '#444', fontSize: '9px' }}>
            {new Date(advisory.last_updated).toLocaleTimeString()}
          </span>
        )}
      </div>

      {!advisory ? (
        <div style={{ color: '#333', padding: '10px', fontFamily: 'monospace', fontSize: '11px' }}>
          Awaiting advisory…
        </div>
      ) : (
        <div style={{ padding: '8px 10px', overflowY: 'auto', flex: 1 }}>
          <div style={SECTION}>
            <div style={LABEL}>Situation</div>
            <div style={BODY}>{advisory.situation_summary}</div>
          </div>

          <div style={SECTION}>
            <div style={LABEL}>Immediate Actions</div>
            <ol style={{ ...BODY, margin: 0, paddingLeft: '16px' }}>
              {(advisory.immediate_actions || []).map((a, i) => (
                <li key={i} style={{ marginBottom: '2px' }}>{a}</li>
              ))}
            </ol>
          </div>

          {advisory.exclusion_zones?.length > 0 && (
            <div style={SECTION}>
              <div style={LABEL}>Exclusion Zones</div>
              {advisory.exclusion_zones.map((z, i) => (
                <div key={i} style={{ ...BODY, color: '#ef5350' }}>
                  {z.radius_m}m @ {z.lat?.toFixed(4)},{z.lon?.toFixed(4)} — {z.reason}
                </div>
              ))}
            </div>
          )}

          <div style={SECTION}>
            <div style={LABEL}>Resources</div>
            <ul style={{ ...BODY, margin: 0, paddingLeft: '14px' }}>
              {(advisory.resource_requirements || []).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>

          {advisory.risk_flags?.length > 0 && (
            <div style={SECTION}>
              <div style={LABEL}>Risk Flags</div>
              {advisory.risk_flags.map((f, i) => (
                <div key={i} style={{ ...BODY, color: '#ffa726' }}>⚠ {f}</div>
              ))}
            </div>
          )}

          <div style={SECTION}>
            <div style={LABEL}>Monitoring</div>
            <div style={BODY}>{advisory.monitoring_status}</div>
          </div>
        </div>
      )}
    </div>
  )
}

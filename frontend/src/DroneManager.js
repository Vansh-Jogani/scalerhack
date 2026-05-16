import L from 'leaflet'
import { DRONE_STATES } from './constants.js'

const LERP_MS = 500

// ── Drone type config ────────────────────────────────────────────────────────

const DRONE_VISUAL = {
  fixed_wing:   { color: '#00CFFF', size: 38, anchor: [19, 19] },
  rotary:       { color: '#00FF88', size: 28, anchor: [14, 14] },
  micro_rotary: { color: '#FFB800', size: 20, anchor: [10, 10] },
}

// ── SVG shapes ───────────────────────────────────────────────────────────────

// Fixed-wing: solid filled arrow pointing up — large, dominant
function fixedWingSVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 38 38" width="38" height="38">
    <g style="filter:drop-shadow(0 0 6px ${color})">
      <polygon points="19,2 36,34 19,27 2,34" fill="${color}" opacity="0.9"/>
      <polygon points="19,2 36,34 19,27 2,34" fill="none" stroke="white" stroke-width="1" opacity="0.6"/>
      <line x1="19" y1="27" x2="19" y2="2" stroke="white" stroke-width="0.8" opacity="0.4"/>
    </g>
  </svg>`
}

// Rotary: diamond body + 4 radiating arms — medium, cross-shaped
function rotarySVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="28" height="28">
    <g style="filter:drop-shadow(0 0 4px ${color})">
      <line x1="14" y1="14" x2="4" y2="4" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="24" y2="4" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="4" y2="24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="24" y2="24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <polygon points="14,4 20,14 14,24 8,14" fill="${color}" opacity="0.85"/>
      <polygon points="14,4 20,14 14,24 8,14" fill="none" stroke="white" stroke-width="0.8"/>
    </g>
  </svg>`
}

// Micro-rotary: circle with crosshairs — small, precision symbol
function microRotarySVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20">
    <g style="filter:drop-shadow(0 0 3px ${color})">
      <circle cx="10" cy="10" r="7" fill="${color}" opacity="0.2" stroke="${color}" stroke-width="1.5"/>
      <circle cx="10" cy="10" r="2.5" fill="${color}"/>
      <line x1="10" y1="1" x2="10" y2="7" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="10" y1="13" x2="10" y2="19" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="1" y1="10" x2="7" y2="10" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="13" y1="10" x2="19" y2="10" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/>
    </g>
  </svg>`
}

function buildSVG(droneType, color) {
  if (droneType === 'fixed_wing') return fixedWingSVG(color)
  if (droneType === 'micro_rotary') return microRotarySVG(color)
  return rotarySVG(color)
}

function lerp(a, b, t) { return a + (b - a) * t }

function bearingDeg(fromLat, fromLon, toLat, toLon) {
  const dLon = toLon - fromLon
  const dLat = toLat - fromLat
  return (Math.atan2(dLon, dLat) * 180) / Math.PI
}

// ── DroneManager ─────────────────────────────────────────────────────────────

class _DroneManager {
  constructor() {
    this._map = null
    this._drones = {}
    this._rafId = null
  }

  init(mapInstance) {
    this._map = mapInstance
    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }

  destroy() {
    if (this._rafId) cancelAnimationFrame(this._rafId)
    this._rafId = null
    this._map = null
  }

  updateDrone(data) {
    if (!this._map) return
    const { drone_id, lat, lon, heading, state, battery_pct, alt, speed, drone_type = 'rotary' } = data
    const visual = DRONE_VISUAL[drone_type] || DRONE_VISUAL.rotary
    const { color, size, anchor } = visual

    if (!this._drones[drone_id]) {
      const svg = buildSVG(drone_type, color)
      const typeLabel = drone_type.replace(/_/g, '-')
      const html = `<div class="drone-marker">
        <div class="drone-svg">${svg}</div>
        <div class="drone-state-badge" style="background:${DRONE_STATES[state] || DRONE_STATES.IDLE}"></div>
      </div>`
      const icon = L.divIcon({ className: '', html, iconSize: [size, size], iconAnchor: anchor })
      const marker = L.marker([lat, lon], { icon, interactive: true }).addTo(this._map)

      const initialState = state || 'IDLE'
      if (initialState === 'IDLE') marker.setOpacity(0)

      marker.bindPopup(() => {
        const d = this._drones[drone_id]
        if (!d) return ''
        return `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
          <div><span style="color:#7A8FA8">ID   </span> ${drone_id}</div>
          <div><span style="color:#7A8FA8">TYPE </span> <span style="color:${color}">${typeLabel}</span></div>
          <div><span style="color:#7A8FA8">STATE</span> ${d.state}</div>
          <div><span style="color:#7A8FA8">BAT  </span> ${d.battery_pct != null ? d.battery_pct.toFixed(0) + '%' : '?'}</div>
          <div><span style="color:#7A8FA8">ALT  </span> ${d.alt != null ? d.alt.toFixed(0) + 'm' : '?'}</div>
          <div><span style="color:#7A8FA8">SPD  </span> ${d.speed != null ? d.speed.toFixed(1) + ' m/s' : '?'}</div>
        </div>`
      }, { className: 'aria-popup' })

      this._drones[drone_id] = {
        marker,
        startLat: lat, startLon: lon,
        targetLat: lat, targetLon: lon,
        currentLat: lat, currentLon: lon,
        animStart: performance.now(),
        bearing: heading || 0,
        state: initialState,
        battery_pct, alt, speed, color, drone_type,
      }
    } else {
      const d = this._drones[drone_id]
      const prevState = d.state
      d.startLat = d.currentLat
      d.startLon = d.currentLon
      d.targetLat = lat
      d.targetLon = lon
      d.animStart = performance.now()
      d.state = state || d.state
      d.battery_pct = battery_pct ?? d.battery_pct
      d.alt = alt ?? d.alt
      d.speed = speed ?? d.speed

      if (prevState === 'IDLE' && d.state !== 'IDLE') d.marker.setOpacity(1)
      if (d.state === 'IDLE') d.marker.setOpacity(0)

      const el = d.marker.getElement()
      if (el) {
        const badge = el.querySelector('.drone-state-badge')
        if (badge) badge.style.background = DRONE_STATES[d.state] || DRONE_STATES.IDLE
      }
    }
  }

  _tick(timestamp) {
    if (!this._map) return

    Object.entries(this._drones).forEach(([, d]) => {
      const elapsed = timestamp - d.animStart
      const t = Math.min(elapsed / LERP_MS, 1)

      const newLat = lerp(d.startLat, d.targetLat, t)
      const newLon = lerp(d.startLon, d.targetLon, t)
      d.currentLat = newLat
      d.currentLon = newLon
      d.marker.setLatLng([newLat, newLon])

      const dLat = d.targetLat - d.startLat
      const dLon = d.targetLon - d.startLon
      if (Math.abs(dLat) > 1e-7 || Math.abs(dLon) > 1e-7) {
        d.bearing = bearingDeg(d.startLat, d.startLon, d.targetLat, d.targetLon)
      }
      const el = d.marker.getElement()
      if (el) {
        const svg = el.querySelector('.drone-svg')
        if (svg) svg.style.transform = `rotate(${d.bearing}deg)`
      }
    })

    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }
}

const DroneManager = new _DroneManager()
export default DroneManager

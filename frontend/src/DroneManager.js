import L from 'leaflet'
import { DRONE_STATES } from './constants.js'

const LERP_MS = 500
const TRAIL_MAX = 20

function lerp(a, b, t) { return a + (b - a) * t }

function bearingDeg(fromLat, fromLon, toLat, toLon) {
  const dLon = toLon - fromLon
  const dLat = toLat - fromLat
  return (Math.atan2(dLon, dLat) * 180) / Math.PI
}

function droneGlowSVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="28" height="28">
    <g style="filter:drop-shadow(0 0 4px ${color})">
      <line x1="14" y1="14" x2="5" y2="5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="23" y2="5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="5" y2="23" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="23" y2="23" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="5" cy="5" r="3.5" fill="none" stroke="white" stroke-width="1"/>
      <circle cx="23" cy="5" r="3.5" fill="none" stroke="white" stroke-width="1"/>
      <circle cx="5" cy="23" r="3.5" fill="none" stroke="white" stroke-width="1"/>
      <circle cx="23" cy="23" r="3.5" fill="none" stroke="white" stroke-width="1"/>
      <circle cx="14" cy="14" r="3" fill="white"/>
    </g>
  </svg>`
}

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
    const { drone_id, lat, lon, heading, state, battery_pct, alt, speed } = data
    const color = '#00FF88'

    if (!this._drones[drone_id]) {
      const html = `<div class="drone-marker">
        <div class="drone-svg">${droneGlowSVG(color)}</div>
        <div class="drone-state-badge" style="background:${DRONE_STATES[state] || DRONE_STATES.IDLE}"></div>
      </div>`
      const icon = L.divIcon({ className: '', html, iconSize: [28, 28], iconAnchor: [14, 14] })
      const marker = L.marker([lat, lon], { icon, interactive: true }).addTo(this._map)

      marker.bindPopup(() => {
        const d = this._drones[drone_id]
        if (!d) return ''
        return `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
          <div><span style="color:#7A8FA8">ID   </span> ${drone_id}</div>
          <div><span style="color:#7A8FA8">STATE</span> ${d.state}</div>
          <div><span style="color:#7A8FA8">BAT  </span> ${d.battery_pct != null ? d.battery_pct.toFixed(0) + '%' : '?'}</div>
          <div><span style="color:#7A8FA8">ALT  </span> ${d.alt != null ? d.alt.toFixed(0) + 'm' : '?'}</div>
          <div><span style="color:#7A8FA8">SPD  </span> ${d.speed != null ? d.speed.toFixed(1) + ' m/s' : '?'}</div>
        </div>`
      }, { className: 'aria-popup' })

      const trail = L.polyline([], {
        color, weight: 1.5, opacity: 0.4, dashArray: '3 3',
      }).addTo(this._map)

      this._drones[drone_id] = {
        marker, trail,
        startLat: lat, startLon: lon,
        targetLat: lat, targetLon: lon,
        currentLat: lat, currentLon: lon,
        animStart: performance.now(),
        bearing: heading || 0,
        trailPts: [[lat, lon]],
        state: state || 'IDLE',
        battery_pct, alt, speed, color,
      }
    } else {
      const d = this._drones[drone_id]
      d.startLat = d.currentLat
      d.startLon = d.currentLon
      d.targetLat = lat
      d.targetLon = lon
      d.animStart = performance.now()
      d.state = state || d.state
      d.battery_pct = battery_pct ?? d.battery_pct
      d.alt = alt ?? d.alt
      d.speed = speed ?? d.speed

      const el = d.marker.getElement()
      if (el) {
        const badge = el.querySelector('.drone-state-badge')
        if (badge) badge.style.background = DRONE_STATES[d.state] || DRONE_STATES.IDLE
      }
    }
  }

  _tick(timestamp) {
    if (!this._map) return

    Object.entries(this._drones).forEach(([drone_id, d]) => {
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

      if (t >= 1) {
        d.trailPts.push([newLat, newLon])
        if (d.trailPts.length > TRAIL_MAX) d.trailPts.shift()
        d.trail.setLatLngs(d.trailPts)
      }
    })

    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }
}

const DroneManager = new _DroneManager()
export default DroneManager

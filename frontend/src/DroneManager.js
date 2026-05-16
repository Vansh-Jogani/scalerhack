import mapboxgl from 'mapbox-gl'
import { DRONE_STATES } from './constants.js'

const LERP_MS = 500
const TRAIL_MAX = 60

// ── Drone type config ────────────────────────────────────────────────────────

const DRONE_VISUAL = {
  fixed_wing:   { color: '#00CFFF', size: 22, anchor: [11, 11] },
  rotary:       { color: '#00FF88', size: 16, anchor: [8, 8] },
  micro_rotary: { color: '#FFB800', size: 12, anchor: [6, 6] },
}

// ── SVG shapes ───────────────────────────────────────────────────────────────

function fixedWingSVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 38 38" width="22" height="22">
    <g style="filter:drop-shadow(0 0 4px ${color})">
      <polygon points="19,2 36,34 19,27 2,34" fill="${color}" opacity="0.9"/>
      <polygon points="19,2 36,34 19,27 2,34" fill="none" stroke="white" stroke-width="1" opacity="0.6"/>
      <line x1="19" y1="27" x2="19" y2="2" stroke="white" stroke-width="0.8" opacity="0.4"/>
    </g>
  </svg>`
}

function rotarySVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="16" height="16">
    <g style="filter:drop-shadow(0 0 3px ${color})">
      <line x1="14" y1="14" x2="4" y2="4" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="24" y2="4" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="4" y2="24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="14" y1="14" x2="24" y2="24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <polygon points="14,4 20,14 14,24 8,14" fill="${color}" opacity="0.85"/>
      <polygon points="14,4 20,14 14,24 8,14" fill="none" stroke="white" stroke-width="0.8"/>
    </g>
  </svg>`
}

function microRotarySVG(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="12" height="12">
    <g style="filter:drop-shadow(0 0 2px ${color})">
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
    const { color, size } = visual

    if (!this._drones[drone_id]) {
      const svg = buildSVG(drone_type, color)
      const typeLabel = drone_type.replace(/_/g, '-')

      const el = document.createElement('div')
      el.style.cssText = `width:${size}px;height:${size}px;cursor:pointer;transition:opacity 0.3s`
      el.innerHTML = svg

      const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false, offset: 14 })
      popup.on('open', () => {
        const d = this._drones[drone_id]
        if (!d) return
        popup.setHTML(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
          <div><span style="color:#7A8FA8">ID   </span> ${drone_id}</div>
          <div><span style="color:#7A8FA8">TYPE </span> <span style="color:${color}">${typeLabel}</span></div>
          <div><span style="color:#7A8FA8">STATE</span> ${d.state}</div>
          <div><span style="color:#7A8FA8">BAT  </span> ${d.battery_pct != null ? d.battery_pct.toFixed(0) + '%' : '?'}</div>
          <div><span style="color:#7A8FA8">ALT  </span> ${d.alt != null ? d.alt.toFixed(0) + 'm' : '?'}</div>
          <div><span style="color:#7A8FA8">SPD  </span> ${d.speed != null ? d.speed.toFixed(1) + ' m/s' : '?'}</div>
        </div>`)
      })

      const marker = new mapboxgl.Marker(el, { anchor: 'center' })
        .setLngLat([lon, lat])
        .setPopup(popup)
        .addTo(this._map)

      // Trail as Mapbox GeoJSON source + line layer
      const trailId = `drone-trail-${drone_id}`
      this._map.addSource(trailId, {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } },
      })
      this._map.addLayer({
        id: trailId,
        type: 'line',
        source: trailId,
        paint: { 'line-color': color, 'line-width': 1.5, 'line-opacity': 0.4, 'line-dasharray': [3, 3] },
      })

      const initialState = state || 'IDLE'
      if (initialState === 'IDLE') el.style.opacity = '0'

      this._drones[drone_id] = {
        marker, trailId,
        startLat: lat, startLon: lon,
        targetLat: lat, targetLon: lon,
        currentLat: lat, currentLon: lon,
        animStart: performance.now(),
        bearing: heading || 0,
        state: initialState,
        trailCoords: [],
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

      const el = d.marker.getElement()
      if (el) {
        if (prevState === 'IDLE' && d.state !== 'IDLE') el.style.opacity = '1'
        if (d.state === 'IDLE') el.style.opacity = '0'
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
      d.marker.setLngLat([newLon, newLat])

      const dLat = d.targetLat - d.startLat
      const dLon = d.targetLon - d.startLon
      if (Math.abs(dLat) > 1e-7 || Math.abs(dLon) > 1e-7) {
        d.bearing = bearingDeg(d.startLat, d.startLon, d.targetLat, d.targetLon)
      }
      const el = d.marker.getElement()
      if (el) el.style.transform = `rotate(${d.bearing}deg)`

      if (t >= 1) {
        d.trailCoords.push([newLon, newLat])
        if (d.trailCoords.length > TRAIL_MAX) d.trailCoords.shift()
        const src = this._map.getSource(d.trailId)
        if (src) src.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: d.trailCoords } })
      }
    })

    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }
}

const DroneManager = new _DroneManager()
export default DroneManager

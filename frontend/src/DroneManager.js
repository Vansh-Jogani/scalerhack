import mapboxgl from 'mapbox-gl'
import { DRONE_STATES, DISASTER_COLOR_MAP } from './constants.js'

const LERP_MS = 500
const TRAIL_MAX = 20

function lerp(a, b, t) {
  return a + (b - a) * t
}

function bearingDeg(fromLat, fromLon, toLat, toLon) {
  const dLon = toLon - fromLon
  const dLat = toLat - fromLat
  const rad = Math.atan2(dLon, dLat)
  return (rad * 180) / Math.PI
}

function droneGlowSVG(color) {
  return `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="28" height="28">
    <style>
      .arm { stroke: white; stroke-width: 1.5; stroke-linecap: round; }
      .rotor { fill: none; stroke: white; stroke-width: 1; }
      .body { fill: white; }
      .glow { filter: drop-shadow(0 0 4px ${color}); }
    </style>
    <g class="glow">
      <!-- Arms -->
      <line class="arm" x1="14" y1="14" x2="5"  y2="5" />
      <line class="arm" x1="14" y1="14" x2="23" y2="5" />
      <line class="arm" x1="14" y1="14" x2="5"  y2="23"/>
      <line class="arm" x1="14" y1="14" x2="23" y2="23"/>
      <!-- Rotors -->
      <circle class="rotor" cx="5"  cy="5"  r="3.5"/>
      <circle class="rotor" cx="23" cy="5"  r="3.5"/>
      <circle class="rotor" cx="5"  cy="23" r="3.5"/>
      <circle class="rotor" cx="23" cy="23" r="3.5"/>
      <!-- Body -->
      <circle class="body" cx="14" cy="14" r="3"/>
    </g>
  </svg>`
}

class _DroneManager {
  constructor() {
    this._map = null
    this._drones = {}
    this._rafId = null
    this._lastTime = 0
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
    const { drone_id, lat, lon, heading, state, battery_pct, alt, speed, disaster_type } = data
    const color = disaster_type ? (DISASTER_COLOR_MAP[disaster_type] || '#00FF88') : '#00FF88'

    if (!this._drones[drone_id]) {
      // Create marker
      const el = document.createElement('div')
      el.className = 'drone-marker'
      el.innerHTML = droneGlowSVG(color)

      const badge = document.createElement('div')
      badge.className = 'drone-state-badge'
      badge.style.background = DRONE_STATES[state] || DRONE_STATES.IDLE
      el.appendChild(badge)

      const svgEl = el.querySelector('svg')

      el.addEventListener('click', (e) => {
        e.stopPropagation()
        const d = this._drones[drone_id]
        if (!d || !this._map) return
        new mapboxgl.Popup({ closeButton: true, maxWidth: '220px' })
          .setLngLat([d.currentLon, d.currentLat])
          .setHTML(`
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
              <div><span style="color:#7A8FA8">ID   </span> ${drone_id}</div>
              <div><span style="color:#7A8FA8">STATE</span> ${d.state}</div>
              <div><span style="color:#7A8FA8">BAT  </span> ${d.battery_pct != null ? d.battery_pct.toFixed(0) + '%' : '?'}</div>
              <div><span style="color:#7A8FA8">ALT  </span> ${d.alt != null ? d.alt.toFixed(0) + 'm' : '?'}</div>
              <div><span style="color:#7A8FA8">SPD  </span> ${d.speed != null ? d.speed.toFixed(1) + ' m/s' : '?'}</div>
            </div>
          `)
          .addTo(this._map)
      })

      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat([lon, lat])
        .addTo(this._map)

      // Create trail source
      const trailId = `drone-trail-${drone_id}`
      if (!this._map.getSource(trailId)) {
        this._map.addSource(trailId, {
          type: 'geojson',
          data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} },
        })
        this._map.addLayer({
          id: trailId,
          type: 'line',
          source: trailId,
          paint: {
            'line-color': color,
            'line-width': 1.5,
            'line-opacity': 0.4,
            'line-dasharray': [3, 3],
          },
        })
      }

      this._drones[drone_id] = {
        marker,
        svgEl,
        badge,
        startLat: lat, startLon: lon,
        targetLat: lat, targetLon: lon,
        currentLat: lat, currentLon: lon,
        animStart: performance.now(),
        bearing: heading || 0,
        trail: [[lon, lat]],
        state: state || 'IDLE',
        battery_pct,
        alt,
        speed,
        color,
      }
    } else {
      // Update existing
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

      // Update badge color
      d.badge.style.background = DRONE_STATES[d.state] || DRONE_STATES.IDLE
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
      d.marker.setLngLat([newLon, newLat])

      // Heading
      const dLat = d.targetLat - d.startLat
      const dLon = d.targetLon - d.startLon
      if (Math.abs(dLat) > 1e-7 || Math.abs(dLon) > 1e-7) {
        d.bearing = bearingDeg(d.startLat, d.startLon, d.targetLat, d.targetLon)
      }
      if (d.svgEl) {
        d.svgEl.style.transform = `rotate(${d.bearing}deg)`
      }

      // Trail — update every completed lerp step
      if (t >= 1) {
        d.trail.push([newLon, newLat])
        if (d.trail.length > TRAIL_MAX) d.trail.shift()
        const trailId = `drone-trail-${drone_id}`
        const src = this._map.getSource(trailId)
        if (src && d.trail.length >= 2) {
          src.setData({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: d.trail },
            properties: {},
          })
        }
      }
    })

    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }
}

const DroneManager = new _DroneManager()
export default DroneManager

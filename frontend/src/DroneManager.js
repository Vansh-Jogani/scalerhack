import mapboxgl from 'mapbox-gl'
import { DRONE_STATES } from './constants.js'

const LERP_MS = 500
const TRAIL_MAX = 20

function lerp(a, b, t) { return a + (b - a) * t }

function bearingDeg(fromLat, fromLon, toLat, toLon) {
  const dLon = toLon - fromLon
  const dLat = toLat - fromLat
  return (Math.atan2(dLon, dLat) * 180) / Math.PI
}

// BeaconDrone — Agent 1 surveillance fixed-wing (directional, pulsing)
function makeBeaconEl(color = '#9C8AFF', size = 36) {
  const w = document.createElement('div')
  w.style.cssText = `position:relative;width:${size}px;height:${size}px;pointer-events:none`
  // Concentric pulse rings
  ;[0, 0.8, 1.6].forEach((delay) => {
    const ring = document.createElement('span')
    ring.style.cssText = `position:absolute;inset:0;border-radius:50%;border:1px solid ${color};opacity:0;animation:beaconRing 2.4s ease-out infinite;animation-delay:${delay}s`
    w.appendChild(ring)
  })
  // Rotation group (heading set dynamically via style.transform)
  const rot = document.createElement('div')
  rot.className = 'beacon-rot'
  rot.style.cssText = `position:absolute;inset:0;transform-origin:center`
  rot.innerHTML = `<svg viewBox="-50 -50 100 100" style="position:absolute;inset:0;overflow:visible">
    <defs>
      <radialGradient id="fov-g" cx="0.5" cy="1" r="1">
        <stop offset="0" stop-color="${color}" stop-opacity="0.18"/>
        <stop offset="0.7" stop-color="${color}" stop-opacity="0.04"/>
        <stop offset="1" stop-color="${color}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <path d="M 0,0 L -16,-44 A 48 48 0 0 1 16,-44 Z" fill="url(#fov-g)"/>
    <path d="M -14,4 L 0,-12 L 14,4 L 8,6 L 0,-2 L -8,6 Z" fill="${color}" opacity="0.92" stroke="rgba(255,255,255,0.6)" stroke-width="0.6"/>
    <path d="M -4,8 L 4,8 L 2,12 L -2,12 Z" fill="${color}" opacity="0.65"/>
  </svg>`
  w.appendChild(rot)
  // Bright beacon core
  const core = document.createElement('span')
  core.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:5px;height:5px;background:white;border-radius:50%;box-shadow:0 0 10px white,0 0 18px ${color},0 0 28px ${color};animation:beaconCore 1.4s ease-in-out infinite`
  w.appendChild(core)
  return w
}

// SwarmDrone — Agent 2 rotary specialist (subtle, reads as a group)
function makeSwarmEl(color = '#ff5a4d', size = 22) {
  const w = document.createElement('div')
  w.style.cssText = `position:relative;width:${size}px;height:${size}px;pointer-events:none`
  const halo = document.createElement('span')
  halo.style.cssText = `position:absolute;inset:-3px;border-radius:50%;background:radial-gradient(circle,${color}1c 0%,transparent 70%)`
  w.appendChild(halo)
  const rot = document.createElement('div')
  rot.className = 'swarm-rot'
  rot.style.cssText = `position:absolute;inset:0;transform-origin:center`
  const rotors = [45,135,225,315].map(deg => {
    const r = 7, rad = deg * Math.PI / 180
    return `<circle cx="${(Math.cos(rad)*r).toFixed(2)}" cy="${(Math.sin(rad)*r).toFixed(2)}" r="1.6" fill="none" stroke="${color}" stroke-width="0.9" opacity="0.55"/>`
  }).join('')
  rot.innerHTML = `<svg viewBox="-12 -12 24 24" style="position:absolute;inset:0;overflow:visible">${rotors}<line x1="-5" y1="-5" x2="5" y2="5" stroke="${color}" stroke-opacity="0.2" stroke-width="0.6"/><line x1="-5" y1="5" x2="5" y2="-5" stroke="${color}" stroke-opacity="0.2" stroke-width="0.6"/></svg>`
  w.appendChild(rot)
  const dot = document.createElement('span')
  dot.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:4px;height:4px;background:${color};border-radius:50%;box-shadow:0 0 5px ${color};animation:swarmBreathe 2.6s ease-in-out infinite`
  w.appendChild(dot)
  return w
}

// MicroDrone — Agent 2 micro_rotary (hexacopter, tight search pattern)
function makeMicroEl(color = '#ff5a4d', size = 16) {
  const w = document.createElement('div')
  w.style.cssText = `position:relative;width:${size}px;height:${size}px;pointer-events:none`
  const rot = document.createElement('div')
  rot.className = 'swarm-rot'
  rot.style.cssText = `position:absolute;inset:0;transform-origin:center`
  // 6 rotor dots at 60° intervals (hexacopter)
  const rotors = [0, 60, 120, 180, 240, 300].map(deg => {
    const r = 6, rad = deg * Math.PI / 180
    return `<circle cx="${(Math.cos(rad) * r).toFixed(2)}" cy="${(Math.sin(rad) * r).toFixed(2)}" r="1.2" fill="${color}" opacity="0.7"/>`
  }).join('')
  rot.innerHTML = `<svg viewBox="-10 -10 20 20" style="position:absolute;inset:0;overflow:visible">
    ${rotors}
    <circle cx="0" cy="0" r="2.5" fill="none" stroke="${color}" stroke-width="0.7" opacity="0.4"/>
  </svg>`
  w.appendChild(rot)
  const dot = document.createElement('span')
  dot.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:3px;height:3px;background:${color};border-radius:50%;box-shadow:0 0 4px ${color};animation:swarmBreathe 1.8s ease-in-out infinite`
  w.appendChild(dot)
  return w
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

  // Satellite offset in geographic degrees for ~40m spacing
  _satelliteOffsets(bearingDeg, lat) {
    const DIST_M = 40
    const dLat = DIST_M / 111320
    const dLon = DIST_M / (111320 * Math.cos(lat * Math.PI / 180))
    // 4 satellites at ±45° / ±135° relative to heading (diamond formation)
    return [45, 135, 225, 315].map((offset) => {
      const a = (bearingDeg + offset) * Math.PI / 180
      return { dLat: Math.cos(a) * dLat, dLon: Math.sin(a) * dLon }
    })
  }

  updateDrone(data) {
    if (!this._map) return
    const { drone_id, lat, lon, heading, state, battery_pct, alt, speed, swarm_leader, drone_type } = data
    const color = '#00FF88'

    if (!this._drones[drone_id]) {
      // Icon selection by drone_type — falls back to ID check for backward compat
      const type = drone_type || (drone_id === 'drone-001' ? 'fixed_wing' : 'rotary')
      let el
      if (type === 'fixed_wing') {
        // Agent 1 surveillance: large beacon; swarm fixed-wings: smaller
        el = drone_id === 'drone-001'
          ? makeBeaconEl('#9C8AFF', 56)
          : makeBeaconEl(color, 32)
      } else if (type === 'micro_rotary') {
        el = makeMicroEl(color, 16)
      } else {
        el = makeSwarmEl(color, 24)
      }

      const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false, offset: 14 })
      popup.on('open', () => {
        const d = this._drones[drone_id]
        if (!d) return
        popup.setHTML(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
          <div><span style="color:#7A8FA8">ID   </span> ${drone_id}</div>
          <div><span style="color:#7A8FA8">TYPE </span> ${d.drone_type || '?'}</div>
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

      // Swarm leader: 4 satellite drones rendered as smaller SwarmDrone icons
      const satellites = []
      if (swarm_leader) {
        for (let i = 0; i < 4; i++) {
          const sEl = makeSwarmEl(color, 18)
          sEl.style.opacity = '0.7'
          const sm = new mapboxgl.Marker(sEl, { anchor: 'center' }).setLngLat([lon, lat]).addTo(this._map)
          satellites.push(sm)
        }
      }

      this._drones[drone_id] = {
        marker, trailId, satellites,
        startLat: lat, startLon: lon,
        targetLat: lat, targetLon: lon,
        currentLat: lat, currentLon: lon,
        animStart: performance.now(),
        bearing: heading || 0,
        trailCoords: [],  // [[lon, lat], ...] — Mapbox order
        state: state || 'IDLE',
        swarm_leader: !!swarm_leader,
        drone_type: type,
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

      // Update beacon core glow color based on state
      const el = d.marker.getElement()
      if (el) {
        const core = el.querySelector('span[style*="beaconCore"], span[style*="swarmBreathe"]')
        if (core && d.state === 'LOITERING') core.style.boxShadow = '0 0 10px #FFB800, 0 0 18px #FFB800'
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
      // Mapbox Marker: setLngLat([lon, lat])
      d.marker.setLngLat([newLon, newLat])

      const dLat = d.targetLat - d.startLat
      const dLon = d.targetLon - d.startLon
      if (Math.abs(dLat) > 1e-7 || Math.abs(dLon) > 1e-7) {
        d.bearing = bearingDeg(d.startLat, d.startLon, d.targetLat, d.targetLon)
      }
      const el = d.marker.getElement()
      if (el) {
        const rot = el.querySelector('.beacon-rot, .swarm-rot')
        if (rot) rot.style.transform = `rotate(${d.bearing}deg)`
      }

      if (t >= 1) {
        d.trailCoords.push([newLon, newLat])
        if (d.trailCoords.length > TRAIL_MAX) d.trailCoords.shift()
        const src = this._map.getSource(d.trailId)
        if (src) src.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: d.trailCoords } })
      }

      // Phase 5: update satellite positions relative to leader heading
      if (d.swarm_leader && d.satellites?.length === 4) {
        const offsets = this._satelliteOffsets(d.bearing, newLat)
        offsets.forEach((off, i) => {
          d.satellites[i].setLngLat([newLon + off.dLon, newLat + off.dLat])
        })
      }
    })

    this._rafId = requestAnimationFrame((t) => this._tick(t))
  }
}

const DroneManager = new _DroneManager()
export default DroneManager

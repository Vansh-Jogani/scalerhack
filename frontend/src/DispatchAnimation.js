import L from 'leaflet'
import { DISASTER_LABELS } from './constants.js'

// ── Geometry helpers ──────────────────────────────────────────────────────────

export function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export function findNearestCentre(polygonVertices, responseCentres) {
  const n = polygonVertices.length
  const centLat = polygonVertices.reduce((s, v) => s + v[1], 0) / n
  const centLon = polygonVertices.reduce((s, v) => s + v[0], 0) / n
  let nearest = null
  let minDist = Infinity
  for (const rc of responseCentres) {
    const d = haversine(centLat, centLon, rc.lat, rc.lon)
    if (d < minDist) { minDist = d; nearest = rc }
  }
  return nearest
}

export function calcBearing(srcLon, srcLat, dstLon, dstLat) {
  const dLon = (dstLon - srcLon) * Math.PI / 180
  const lat1 = srcLat * Math.PI / 180
  const lat2 = dstLat * Math.PI / 180
  const y = Math.sin(dLon) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon)
  return Math.atan2(y, x)
}

// ── SVG factories ─────────────────────────────────────────────────────────────

function fixedWingSVG(colour) {
  return `<svg width="34" height="32" viewBox="-17 -16 34 32" xmlns="http://www.w3.org/2000/svg">
    <polygon points="0,-13 -17,3 -9,8 -2,5 -5,15 0,12 5,15 2,5 9,8 17,3"
             fill="${colour}" stroke="rgba(255,255,255,0.55)" stroke-width="0.8"/>
    <circle cx="0" cy="-8" r="2.5" fill="white"/>
  </svg>`
}

function arrowSVG(colour) {
  return `<svg width="14" height="20" viewBox="-7 -10 14 20" xmlns="http://www.w3.org/2000/svg">
    <polygon points="0,-10 -7,10 7,10" fill="${colour}"/>
  </svg>`
}

function rotaryDroneSVG(disasterColour, stateColour) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
    <line x1="14" y1="14" x2="20" y2="8"  stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="14" y1="14" x2="8"  y2="8"  stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="14" y1="14" x2="20" y2="20" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="14" y1="14" x2="8"  y2="20" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="20" cy="8"  r="4" fill="${disasterColour}" stroke="white" stroke-width="0.5"/>
    <circle cx="8"  cy="8"  r="4" fill="${disasterColour}" stroke="white" stroke-width="0.5"/>
    <circle cx="20" cy="20" r="4" fill="${disasterColour}" stroke="white" stroke-width="0.5"/>
    <circle cx="8"  cy="20" r="4" fill="${disasterColour}" stroke="white" stroke-width="0.5"/>
    <circle cx="14" cy="14" r="4" fill="white"/>
    <circle cx="14" cy="14" r="2.5" fill="${stateColour}"/>
  </svg>`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ease = (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t

function fireAgentEvent(agent, text) {
  window.dispatchEvent(new CustomEvent('aria-agent-event', { detail: { agent, text } }))
}

// ── DispatchAnimation (Leaflet) ──────────────────────────────────────────────

class DispatchAnimation {
  constructor(map, { srcGeo, dstGeo, droneCount, disasterColour, disasterType }) {
    this._map         = map
    this._src         = srcGeo
    this._dst         = dstGeo
    this._N           = droneCount
    this._colour      = disasterColour
    this._type        = disasterType

    this._rafId       = null
    this._completeCb  = null

    this._fwEl        = null
    this._fwMarker    = null
    this._orbitAngle  = 0
    this._fwTrail     = null
    this._fwTrailPts  = []

    this._arrowEl     = null
    this._arrowMarker = null
    this._dispatchTrail = null

    this._droneEls       = []
    this._droneMarkers   = []
    this._droneAngles    = []
    this._droneTrails    = []
    this._droneTrailPts  = []
    this._patrolCenters  = []

    this._assessPanel = null
    this._burstCircles = []

    this._Rx = 0.0014
    this._Ry = 0.0014 * 0.7
  }

  onComplete(cb) { this._completeCb = cb }

  start() { this._phase1_travel() }

  stop() {
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null }
    if (this._fwMarker) { this._map.removeLayer(this._fwMarker); this._fwMarker = null }
    if (this._fwTrail) { this._map.removeLayer(this._fwTrail); this._fwTrail = null }
    if (this._arrowMarker) { this._map.removeLayer(this._arrowMarker); this._arrowMarker = null }
    if (this._dispatchTrail) { this._map.removeLayer(this._dispatchTrail); this._dispatchTrail = null }
    for (const m of this._droneMarkers) this._map.removeLayer(m)
    for (const t of this._droneTrails) this._map.removeLayer(t)
    for (const c of this._burstCircles) this._map.removeLayer(c)
    this._droneMarkers = []
    this._droneTrails = []
    this._droneEls = []
    this._burstCircles = []
    if (this._assessPanel?.parentNode) {
      this._assessPanel.parentNode.removeChild(this._assessPanel)
      this._assessPanel = null
    }
  }

  // ── Internal helpers ───────────────────────────────────────────────────────

  _orbitPoint(a) {
    return {
      lon: this._dst.lon + this._Rx * Math.cos(a),
      lat: this._dst.lat + this._Ry * Math.sin(a),
    }
  }

  _orbitEntry() {
    const a0 = Math.atan2(
      (this._src.lat - this._dst.lat) / this._Ry,
      (this._src.lon - this._dst.lon) / this._Rx,
    )
    return { angle: a0, pt: this._orbitPoint(a0) }
  }

  _fwHeadingDeg(a) {
    return (Math.atan2(Math.cos(a) * this._Ry, -Math.sin(a) * this._Rx) + Math.PI / 2) * 180 / Math.PI
  }

  _advanceFwOrbit() {
    this._orbitAngle += 0.038
    const pt = this._orbitPoint(this._orbitAngle)
    if (this._fwMarker) this._fwMarker.setLatLng([pt.lat, pt.lon])
    if (this._fwEl) this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(this._orbitAngle)}deg)`
    this._fwTrailPts.push([pt.lat, pt.lon])
    if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
    if (this._fwTrail) this._fwTrail.setLatLngs(this._fwTrailPts)
  }

  // ── Phase 1: Fixed-wing departs to orbit entry point ──────────────────────

  _phase1_travel() {
    const { angle: a0, pt: entry } = this._orbitEntry()
    this._orbitAngle = a0

    fireAgentEvent('ORCHESTRATOR', 'SURVEILLANCE_ACTIVE — Agent 1 dispatched · fixed-wing en route')

    this._fwTrail = L.polyline([], {
      color: this._colour, weight: 1.5, dashArray: '4 4', opacity: 0.45,
    }).addTo(this._map)

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, entry.lon, entry.lat) * 180 / Math.PI
    const fwHtml = `<div class="fw-icon" style="width:34px;height:34px;transform:rotate(${bearingDeg}deg)">${fixedWingSVG(this._colour)}</div>`
    const icon = L.divIcon({ className: '', html: fwHtml, iconSize: [34, 32], iconAnchor: [17, 16] })
    this._fwMarker = L.marker([this._src.lat, this._src.lon], { icon, interactive: false }).addTo(this._map)
    this._fwEl = this._fwMarker.getElement()?.querySelector('.fw-icon') || null

    const animStart = performance.now()
    const srcLat = this._src.lat, srcLon = this._src.lon
    const dstLat = entry.lat, dstLon = entry.lon

    const tick = (now) => {
      const t = Math.min((now - animStart) / 2200, 1)
      const te = ease(t)
      const lat = srcLat + (dstLat - srcLat) * te
      const lon = srcLon + (dstLon - srcLon) * te

      this._fwMarker.setLatLng([lat, lon])
      this._fwTrailPts.push([lat, lon])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      this._fwTrail.setLatLngs(this._fwTrailPts)

      if (t < 1) {
        this._rafId = requestAnimationFrame(tick)
      } else {
        this._rafId = null
        this._phase2_orbit(a0)
      }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 2: Surveillance orbit — 1.5 turns ───────────────────────────────

  _phase2_orbit(startAngle) {
    fireAgentEvent('AGENT_1', 'On station — thermal scan active · orbiting zone')

    const totalAngle = 1.5 * 2 * Math.PI
    let accumulated = 0
    let a = startAngle

    const tick = () => {
      a += 0.038
      accumulated += 0.038

      const pt = this._orbitPoint(a)
      this._fwMarker.setLatLng([pt.lat, pt.lon])
      if (this._fwEl) this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(a)}deg)`

      this._fwTrailPts.push([pt.lat, pt.lon])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      if (this._fwTrail) this._fwTrail.setLatLngs(this._fwTrailPts)
      this._orbitAngle = a

      if (accumulated < totalAngle) {
        this._rafId = requestAnimationFrame(tick)
      } else {
        this._rafId = null
        this._phase3_assessment()
      }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 3: Assessment panel + launch Agent 2 concurrently ──────────────

  _phase3_assessment() {
    const typeLabel = DISASTER_LABELS[this._type.toUpperCase()] ||
      this._type.toUpperCase().replace(/_/g, ' ')

    fireAgentEvent('AGENT_1', `Classification: ${typeLabel} · confidence 94% · ${this._N} drones required`)

    const c = this._colour
    const row = (label, value, accent = false) =>
      `<div style="display:flex;justify-content:space-between;gap:20px;line-height:2">
        <span style="color:${accent ? c : '#7A8FA8'}">${label}</span>
        <span style="${accent ? `color:${c};font-weight:700` : ''}">${value}</span>
      </div>`

    const panel = document.createElement('div')
    panel.style.cssText = [
      'position:absolute', 'top:14px', 'right:14px',
      'background:#0d1420',
      `border:1px solid ${c}`,
      'border-radius:4px',
      'padding:10px 14px',
      'font-family:JetBrains Mono,monospace',
      'font-size:10px',
      'color:#E8EDF5',
      'min-width:240px',
      'opacity:0',
      'transition:opacity 500ms ease',
      'pointer-events:none',
      'z-index:1000',
    ].join(';')

    panel.innerHTML = `
      <div style="color:${c};font-weight:600;margin-bottom:8px;letter-spacing:0.05em">
        AGENT 1 — ZONE ANALYSIS COMPLETE
      </div>
      ${row('Incident type', typeLabel)}
      ${row('Agent 1 confidence', '94%')}
      ${row('Thermal signatures', `${this._N} detected`)}
      ${row('Affected area', '~2,400 m²')}
      ${row('Spread vector', 'NNE · 12 km/h')}
      ${row('Drones recommended', String(this._N), true)}
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid ${c}40;color:${c};letter-spacing:0.05em">
        DEPLOYING ${this._N} RESPONSE DRONES
      </div>
    `

    this._map.getContainer().appendChild(panel)
    this._assessPanel = panel
    requestAnimationFrame(() => { panel.style.opacity = '1' })

    this._phase4_dispatch()

    setTimeout(() => {
      panel.style.opacity = '0'
      setTimeout(() => {
        if (panel.parentNode) panel.parentNode.removeChild(panel)
        if (this._assessPanel === panel) this._assessPanel = null
        if (this._fwEl) this._fwEl.style.opacity = '0.5'
      }, 500)
    }, 2600)
  }

  // ── Phase 4: Dispatch arrow travels to zone centroid ──────────────────────

  _phase4_dispatch() {
    fireAgentEvent('ORCHESTRATOR', `SWARM_ACTIVE — Agent 2 deploying ${this._N} response drones`)

    this._dispatchTrail = L.polyline([], {
      color: this._colour, weight: 1.5, dashArray: '4 4', opacity: 0.45,
    }).addTo(this._map)

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, this._dst.lon, this._dst.lat) * 180 / Math.PI
    const arrowHtml = `<div class="arrow-icon" style="width:14px;height:20px;transform:rotate(${bearingDeg}deg)">${arrowSVG(this._colour)}</div>`
    const icon = L.divIcon({ className: '', html: arrowHtml, iconSize: [14, 20], iconAnchor: [7, 10] })
    this._arrowMarker = L.marker([this._src.lat, this._src.lon], { icon, interactive: false }).addTo(this._map)
    this._arrowEl = this._arrowMarker.getElement()?.querySelector('.arrow-icon') || null

    const trailPts = []
    const animStart = performance.now()
    const srcLat = this._src.lat, srcLon = this._src.lon
    const dstLat = this._dst.lat, dstLon = this._dst.lon

    const tick = (now) => {
      const t = Math.min((now - animStart) / 1900, 1)
      const te = ease(t)
      const lat = srcLat + (dstLat - srcLat) * te
      const lon = srcLon + (dstLon - srcLon) * te

      this._arrowMarker.setLatLng([lat, lon])
      trailPts.push([lat, lon])
      if (trailPts.length > 60) trailPts.shift()
      this._dispatchTrail.setLatLngs(trailPts)

      if (t < 1) {
        this._rafId = requestAnimationFrame(tick)
      } else {
        this._rafId = null
        this._phase5_burst()
      }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 5: Burst — arrow gone, rings expand, drones spawn ──────────────

  _phase5_burst() {
    if (this._arrowMarker) { this._map.removeLayer(this._arrowMarker); this._arrowMarker = null }
    if (this._fwEl) this._fwEl.style.opacity = '0.4'

    fireAgentEvent('AGENT_2', 'Swarm on target — establishing patrol pattern')

    const burstStart = performance.now()
    const ring1 = L.circle([this._dst.lat, this._dst.lon], {
      radius: 0, color: this._colour, fillColor: 'transparent',
      weight: 2, opacity: 0.6, fill: false,
    }).addTo(this._map)
    const ring2 = L.circle([this._dst.lat, this._dst.lon], {
      radius: 0, color: this._colour, fillColor: 'transparent',
      weight: 1.5, opacity: 0.6, fill: false,
    }).addTo(this._map)
    this._burstCircles.push(ring1, ring2)

    const animateBurst = (now) => {
      const elapsed = now - burstStart
      const t1 = Math.min(elapsed / 600, 1)
      ring1.setRadius(t1 * 200)
      ring1.setStyle({ opacity: 0.6 * (1 - t1) })
      if (elapsed > 200) {
        const t2 = Math.min((elapsed - 200) / 900, 1)
        ring2.setRadius(t2 * 200)
        ring2.setStyle({ opacity: 0.6 * (1 - t2) })
      }
      if (elapsed < 1200) {
        requestAnimationFrame(animateBurst)
      } else {
        this._map.removeLayer(ring1)
        this._map.removeLayer(ring2)
        this._burstCircles = this._burstCircles.filter(c => c !== ring1 && c !== ring2)
      }
    }
    requestAnimationFrame(animateBurst)

    for (let i = 0; i < this._N; i++) {
      const angle = (i / this._N) * 2 * Math.PI + (Math.random() - 0.5) * 0.4
      this._patrolCenters.push({
        lon: this._dst.lon + Math.cos(angle) * 0.0006,
        lat: this._dst.lat + Math.sin(angle) * 0.0006,
      })
      this._droneAngles.push(angle)
      this._droneTrailPts.push([])

      const trail = L.polyline([], {
        color: this._colour, weight: 1, dashArray: '3 3', opacity: 0.35,
      }).addTo(this._map)
      this._droneTrails.push(trail)

      const droneHtml = `<div class="dispatch-drone" style="width:28px;height:28px;transform:scale(0.3);opacity:0;transition:transform 600ms ease-out, opacity 600ms ease-out">${rotaryDroneSVG(this._colour, '#00FF88')}</div>`
      const droneIcon = L.divIcon({ className: '', html: droneHtml, iconSize: [28, 28], iconAnchor: [14, 14] })
      const marker = L.marker([this._dst.lat, this._dst.lon], { icon: droneIcon, interactive: false }).addTo(this._map)
      this._droneMarkers.push(marker)

      const el = marker.getElement()?.querySelector('.dispatch-drone') || null
      this._droneEls.push(el)

      requestAnimationFrame(() => {
        if (el) { el.style.transform = 'scale(1)'; el.style.opacity = '1' }
      })
    }

    const moveStart = performance.now()
    const centLat = this._dst.lat, centLon = this._dst.lon

    const moveTick = (now) => {
      const t = Math.min((now - moveStart) / 800, 1)
      const te = ease(t)

      for (let i = 0; i < this._N; i++) {
        const pc = this._patrolCenters[i]
        const lat = centLat + (pc.lat - centLat) * te
        const lon = centLon + (pc.lon - centLon) * te
        this._droneMarkers[i].setLatLng([lat, lon])
      }

      this._advanceFwOrbit()

      if (t < 1) {
        this._rafId = requestAnimationFrame(moveTick)
      } else {
        for (const el of this._droneEls) { if (el) el.style.transition = 'none' }
        this._rafId = null
        this._phase6_patrol()
      }
    }
    this._rafId = requestAnimationFrame(moveTick)
  }

  // ── Phase 6: Continuous patrol ────────────────────────────────────────────

  _phase6_patrol() {
    fireAgentEvent('AGENT_2', `Zone coverage active · ${this._N} drones monitoring`)

    if (this._completeCb) this._completeCb()

    const tick = () => {
      this._advanceFwOrbit()

      for (let i = 0; i < this._N; i++) {
        const dir = i % 2 === 0 ? 1 : -1
        this._droneAngles[i] += dir * 0.04

        const pc = this._patrolCenters[i]
        const a = this._droneAngles[i]
        const lon = pc.lon + Math.cos(a) * 0.00016
        const lat = pc.lat + Math.sin(a) * 0.00016

        this._droneMarkers[i].setLatLng([lat, lon])

        const hDeg = (a + (dir > 0 ? Math.PI / 2 : -Math.PI / 2)) * 180 / Math.PI
        if (this._droneEls[i]) this._droneEls[i].style.transform = `rotate(${hDeg}deg)`

        this._droneTrailPts[i].push([lat, lon])
        if (this._droneTrailPts[i].length > 20) this._droneTrailPts[i].shift()
        this._droneTrails[i].setLatLngs(this._droneTrailPts[i])
      }

      this._rafId = requestAnimationFrame(tick)
    }
    this._rafId = requestAnimationFrame(tick)
  }
}

export default DispatchAnimation

import mapboxgl from 'mapbox-gl'
import { DISASTER_LABELS } from './constants.js'

// ── Geometry helpers ─────────────────────────────────────────────────────────

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
  let nearest = null, minDist = Infinity
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

// Convert geographic meters to approximate screen pixels at current map zoom/lat
function metersToPixels(map, lat, meters) {
  const metersPerPx = (40075016.686 * Math.cos(lat * Math.PI / 180)) / (256 * Math.pow(2, map.getZoom()))
  return Math.max(2, meters / metersPerPx)
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

function droneWithPayloadSVG(disasterColour, stateColour, disasterType) {
  const type = (disasterType || '').toLowerCase()

  const payloads = {
    fire: `
      <line x1="14" y1="28" x2="14" y2="33" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/>
      <path d="M12 32 Q14 28.5 16 32 Q16.5 30 14 28 Q11.5 30 12 32Z" fill="#FF8C00"/>
      <rect x="10.5" y="32" width="7" height="10" rx="1.5" fill="${disasterColour}" stroke="rgba(255,255,255,0.4)" stroke-width="0.5"/>
      <rect x="10" y="31.5" width="8" height="2" rx="1" fill="#AA0000"/>
    `,
    flood: `
      <line x1="14" y1="28" x2="14" y2="33" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/>
      <rect x="9" y="33" width="10" height="9" rx="1.5" fill="#2196F3" stroke="rgba(255,255,255,0.4)" stroke-width="0.5"/>
      <path d="M9 37 Q11.5 35 14 37 Q16.5 35 19 37" stroke="rgba(255,255,255,0.7)" stroke-width="0.8" fill="none"/>
    `,
    structural_collapse: `
      <line x1="14" y1="28" x2="14" y2="33" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/>
      <rect x="9" y="33" width="10" height="9" rx="1" fill="#FF8C42" stroke="rgba(255,255,255,0.4)" stroke-width="0.5"/>
      <text x="14" y="41" text-anchor="middle" fill="white" font-family="monospace" font-size="5" font-weight="bold">SOS</text>
    `,
    industrial_hazard: `
      <line x1="14" y1="28" x2="14" y2="33" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/>
      <polygon points="14,33 9,42 19,42" fill="#9E9E9E" stroke="rgba(255,255,255,0.4)" stroke-width="0.5"/>
      <text x="14" y="41" text-anchor="middle" fill="#FFE566" font-family="monospace" font-size="7" font-weight="bold">!</text>
    `,
    maritime_sar: `
      <line x1="14" y1="28" x2="14" y2="33" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/>
      <circle cx="14" cy="38" r="5" fill="none" stroke="#00CED1" stroke-width="2.5"/>
      <circle cx="14" cy="38" r="2" fill="#00CED1"/>
    `,
  }

  const payload = payloads[type] || payloads.fire

  return `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="48" viewBox="0 0 28 48">
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
    ${payload}
  </svg>`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ease = (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t

let _animCounter = 0

function fireAgentEvent(agent, text) {
  window.dispatchEvent(new CustomEvent('aria-agent-event', { detail: { agent, text } }))
}

// Helper: add a GeoJSON trail source+layer, return {sourceId, layerId, update(coords)}
function addTrail(map, colour, uid) {
  const sid = `da-trail-${uid}`
  map.addSource(sid, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } } })
  map.addLayer({ id: sid, type: 'line', source: sid, paint: { 'line-color': colour, 'line-width': 1.5, 'line-dasharray': [4, 4], 'line-opacity': 0.45 } })
  return {
    sid,
    update(coords) { const s = map.getSource(sid); if (s) s.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates } }) },
    remove() {
      if (map.getLayer(sid)) map.removeLayer(sid)
      if (map.getSource(sid)) map.removeSource(sid)
    },
  }
}

// ── DispatchAnimation ─────────────────────────────────────────────────────────

class DispatchAnimation {
  constructor(map, { srcGeo, dstGeo, droneCount, disasterColour, disasterType }) {
    this._map     = map
    this._src     = srcGeo
    this._dst     = dstGeo
    this._N       = droneCount
    this._colour  = disasterColour
    this._type    = disasterType
    this._uid     = _animCounter++

    this._rafId       = null
    this._launchTimer = null
    this._completeCb  = null

    this._fwEl        = null
    this._fwMarker    = null   // mapboxgl.Marker
    this._orbitAngle  = 0
    this._fwTrail     = null   // trail object from addTrail()
    this._fwTrailPts  = []

    this._arrowEl     = null
    this._arrowMarker = null
    this._dispatchTrail = null

    this._droneEls       = []
    this._droneMarkers   = []   // mapboxgl.Marker[]
    this._droneAngles    = []
    this._patrolCenters  = []
    this._droneAngles    = []

    this._assessPanel  = null
    this._burstMarkers = []   // mapboxgl.Marker[] for burst rings

    this._Rx = 0.0014
    this._Ry = 0.0014 * 0.7
  }

  onComplete(cb) { this._completeCb = cb }
  start() { this._phase1_travel() }

  stop() {
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null }
    if (this._fwMarker) { this._fwMarker.remove(); this._fwMarker = null }
    if (this._fwTrail) { this._fwTrail.remove(); this._fwTrail = null }
    if (this._arrowMarker) { this._arrowMarker.remove(); this._arrowMarker = null }
    if (this._dispatchTrail) { this._dispatchTrail.remove(); this._dispatchTrail = null }
    for (const m of this._droneMarkers) m.remove()
    for (const t of this._droneTrails) t.remove()
    for (const m of this._burstMarkers) m.remove()
    this._droneMarkers = []; this._droneTrails = []; this._droneEls = []; this._burstMarkers = []
    if (this._assessPanel?.parentNode) {
      this._assessPanel.parentNode.removeChild(this._assessPanel)
      this._assessPanel = null
    }
  }

  // ── Internal helpers ──────────────────────────────────────────────────────

  _orbitPoint(a) {
    return { lon: this._dst.lon + this._Rx * Math.cos(a), lat: this._dst.lat + this._Ry * Math.sin(a) }
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
    if (this._fwMarker) this._fwMarker.setLngLat([pt.lon, pt.lat])
    if (this._fwEl) this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(this._orbitAngle)}deg)`
    this._fwTrailPts.push([pt.lon, pt.lat])
    if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
    if (this._fwTrail) this._fwTrail.update(this._fwTrailPts)
  }

  // ── Phase 1: Fixed-wing departs ───────────────────────────────────────────

  _phase1_travel() {
    const { angle: a0, pt: entry } = this._orbitEntry()
    this._orbitAngle = a0

    fireAgentEvent('ORCHESTRATOR', 'SURVEILLANCE_ACTIVE — Agent 1 dispatched · fixed-wing en route')

    this._fwTrail = addTrail(this._map, this._colour, `fw-${this._uid}`)

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, entry.lon, entry.lat) * 180 / Math.PI
    const fwEl = document.createElement('div')
    fwEl.className = 'fw-icon'
    fwEl.style.cssText = `width:34px;height:34px;transform:rotate(${bearingDeg}deg)`
    fwEl.innerHTML = fixedWingSVG(this._colour)
    this._fwMarker = new mapboxgl.Marker(fwEl, { anchor: 'center' })
      .setLngLat([this._src.lon, this._src.lat])
      .addTo(this._map)
    this._fwEl = fwEl

    const animStart = performance.now()
    const srcLat = this._src.lat, srcLon = this._src.lon
    const dstLat = entry.lat, dstLon = entry.lon

    const tick = (now) => {
      const t = Math.min((now - animStart) / 2200, 1)
      const te = ease(t)
      const lat = srcLat + (dstLat - srcLat) * te
      const lon = srcLon + (dstLon - srcLon) * te
      this._fwMarker.setLngLat([lon, lat])
      this._fwTrailPts.push([lon, lat])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      this._fwTrail.update(this._fwTrailPts)
      if (t < 1) { this._rafId = requestAnimationFrame(tick) } else { this._rafId = null; this._phase2_orbit(a0) }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 2: Surveillance orbit ───────────────────────────────────────────

  _phase2_orbit(startAngle) {
    fireAgentEvent('AGENT_1', 'On station — thermal scan active · orbiting zone')
    const totalAngle = 1.5 * 2 * Math.PI
    let accumulated = 0, a = startAngle
    const tick = () => {
      a += 0.038; accumulated += 0.038
      const pt = this._orbitPoint(a)
      this._fwMarker.setLngLat([pt.lon, pt.lat])
      if (this._fwEl) this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(a)}deg)`
      this._fwTrailPts.push([pt.lon, pt.lat])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      if (this._fwTrail) this._fwTrail.update(this._fwTrailPts)
      this._orbitAngle = a
      if (accumulated < totalAngle) { this._rafId = requestAnimationFrame(tick) }
      else { this._rafId = null; this._phase3_assessment() }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 3: Assessment panel ─────────────────────────────────────────────

  _phase3_assessment() {
    const typeLabel = DISASTER_LABELS[this._type.toUpperCase()] || this._type.toUpperCase().replace(/_/g, ' ')
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
      'background:#0d1420', `border:1px solid ${c}`, 'border-radius:4px',
      'padding:10px 14px', "font-family:'JetBrains Mono',monospace", 'font-size:10px',
      'color:#E8EDF5', 'min-width:240px', 'opacity:0', 'transition:opacity 500ms ease',
      'pointer-events:none', 'z-index:1000',
    ].join(';')
    panel.innerHTML = `
      <div style="color:${c};font-weight:600;margin-bottom:8px;letter-spacing:0.05em">AGENT 1 — ZONE ANALYSIS COMPLETE</div>
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

  // ── Phase 4: Dispatch arrow ───────────────────────────────────────────────

  _phase4_dispatch() {
    fireAgentEvent('ORCHESTRATOR', `SWARM_ACTIVE — Agent 2 deploying ${this._N} response drones`)
    this._dispatchTrail = addTrail(this._map, this._colour, `arrow-${this._uid}`)

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, this._dst.lon, this._dst.lat) * 180 / Math.PI
    const arrowEl = document.createElement('div')
    arrowEl.className = 'arrow-icon'
    arrowEl.style.cssText = `width:14px;height:20px;transform:rotate(${bearingDeg}deg)`
    arrowEl.innerHTML = arrowSVG(this._colour)
    this._arrowMarker = new mapboxgl.Marker(arrowEl, { anchor: 'center' })
      .setLngLat([this._src.lon, this._src.lat])
      .addTo(this._map)
    this._arrowEl = arrowEl

    const trailPts = []
    const animStart = performance.now()
    const srcLat = this._src.lat, srcLon = this._src.lon
    const dstLat = this._dst.lat, dstLon = this._dst.lon

    const tick = (now) => {
      const t = Math.min((now - animStart) / 1900, 1)
      const te = ease(t)
      const lat = srcLat + (dstLat - srcLat) * te
      const lon = srcLon + (dstLon - srcLon) * te
      this._arrowMarker.setLngLat([lon, lat])
      trailPts.push([lon, lat])
      if (trailPts.length > 60) trailPts.shift()
      this._dispatchTrail.update(trailPts)
      if (t < 1) { this._rafId = requestAnimationFrame(tick) } else { this._rafId = null; this._phase5_burst() }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 5: Burst rings + swarm spawn ───────────────────────────────────

  _phase5_burst() {
    if (this._arrowMarker) { this._arrowMarker.remove(); this._arrowMarker = null }
    if (this._fwEl) this._fwEl.style.opacity = '0.4'
    fireAgentEvent('AGENT_2', 'Swarm on target — establishing patrol pattern')

    const { lat: dLat, lon: dLon } = this._dst
    const burstStart = performance.now()
    const map = this._map

    // Two burst rings as DOM elements via mapboxgl.Marker, animated via width/height
    const makeRingMarker = () => {
      const el = document.createElement('div')
      el.style.cssText = `width:0;height:0;border-radius:50%;border:2px solid ${this._colour};opacity:0.7;pointer-events:none;box-sizing:border-box;transform:translate(-50%,-50%)`
      const m = new mapboxgl.Marker(el, { anchor: 'center' }).setLngLat([dLon, dLat]).addTo(map)
      this._burstMarkers.push(m)
      return { marker: m, el }
    }

    const ring1 = makeRingMarker()
    const ring2 = makeRingMarker()

    const animateBurst = (now) => {
      const elapsed = now - burstStart
      const t1 = Math.min(elapsed / 600, 1)
      const px1 = metersToPixels(map, dLat, 200 * t1) * 2
      ring1.el.style.width = `${px1}px`; ring1.el.style.height = `${px1}px`
      ring1.el.style.opacity = String(0.7 * (1 - t1))
      if (elapsed > 200) {
        const t2 = Math.min((elapsed - 200) / 900, 1)
        const px2 = metersToPixels(map, dLat, 200 * t2) * 2
        ring2.el.style.width = `${px2}px`; ring2.el.style.height = `${px2}px`
        ring2.el.style.opacity = String(0.7 * (1 - t2))
      }
      if (elapsed < 1200) { requestAnimationFrame(animateBurst) }
      else { ring1.marker.remove(); ring2.marker.remove(); this._burstMarkers = this._burstMarkers.filter(m => m !== ring1.marker && m !== ring2.marker) }
    }
    requestAnimationFrame(animateBurst)

    // Spawn N drones
    for (let i = 0; i < this._N; i++) {
      const angle = (i / this._N) * 2 * Math.PI + (Math.random() - 0.5) * 0.4
      this._patrolCenters.push({ lon: dLon + Math.cos(angle) * 0.0006, lat: dLat + Math.sin(angle) * 0.0006 })
      this._droneAngles.push(angle)

      const trail = addTrail(this._map, this._colour, `d${i}-${this._uid}`)
      this._droneTrails.push(trail)

      const droneEl = document.createElement('div')
      droneEl.className = 'dispatch-drone'
      droneEl.style.cssText = 'width:28px;height:28px;transform:scale(0.3);opacity:0;transition:transform 600ms ease-out,opacity 600ms ease-out'
      droneEl.innerHTML = rotaryDroneSVG(this._colour, '#00FF88')
      const m = new mapboxgl.Marker(droneEl, { anchor: 'center' })
        .setLngLat([dLon, dLat])
        .addTo(this._map)
      this._droneMarkers.push(m)
      this._droneEls.push(droneEl)

      requestAnimationFrame(() => { droneEl.style.transform = 'scale(1)'; droneEl.style.opacity = '1' })
    }

    const moveStart = performance.now()
    const moveTick = (now) => {
      const t = Math.min((now - moveStart) / 800, 1)
      const te = ease(t)
      for (let i = 0; i < this._N; i++) {
        const pc = this._patrolCenters[i]
        const lat = dLat + (pc.lat - dLat) * te
        const lon = dLon + (pc.lon - dLon) * te
        this._droneMarkers[i].setLngLat([lon, lat])
      }
      this._advanceFwOrbit()
      if (t < 1) { this._rafId = requestAnimationFrame(moveTick) }
      else {
        for (const el of this._droneEls) { if (el) el.style.transition = 'none' }
        this._rafId = null; this._phase6_patrol()
      }
    }
    this._rafId = requestAnimationFrame(moveTick)
  }

  // ── Phase 6: Continuous patrol — fixed-wing only ─────────────────────────

  _phase6_patrol() {
    fireAgentEvent('AGENT_2', `Zone coverage active · ${this._N} drones monitoring`)
    if (this._completeCb) this._completeCb()

    // Only the fixed-wing continues orbiting — rotary drones appear via telemetry
    const tick = () => {
      this._advanceFwOrbit()
      for (let i = 0; i < this._N; i++) {
        const dir = i % 2 === 0 ? 1 : -1
        this._droneAngles[i] += dir * 0.04
        const pc = this._patrolCenters[i]
        const a = this._droneAngles[i]
        const lon = pc.lon + Math.cos(a) * 0.00016
        const lat = pc.lat + Math.sin(a) * 0.00016
        this._droneMarkers[i].setLngLat([lon, lat])
        const hDeg = (a + (dir > 0 ? Math.PI / 2 : -Math.PI / 2)) * 180 / Math.PI
        if (this._droneEls[i]) this._droneEls[i].style.transform = `rotate(${hDeg}deg)`
        this._droneTrailPts[i].push([lon, lat])
        if (this._droneTrailPts[i].length > 20) this._droneTrailPts[i].shift()
        this._droneTrails[i].update(this._droneTrailPts[i])
      }
      this._rafId = requestAnimationFrame(tick)
    }
    this._rafId = requestAnimationFrame(tick)
  }
}

export default DispatchAnimation

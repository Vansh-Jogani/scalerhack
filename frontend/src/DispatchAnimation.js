import mapboxgl from 'mapbox-gl'
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

export function geoToPixel(map, lng, lat) {
  return map.project([lng, lat])
}

export function calcBearing(srcLng, srcLat, dstLng, dstLat) {
  const dLon = (dstLng - srcLng) * Math.PI / 180
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

// ── Helpers ───────────────────────────────────────────────────────────────────

const ease = (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t

function fireAgentEvent(agent, text) {
  window.dispatchEvent(new CustomEvent('aria-agent-event', { detail: { agent, text } }))
}

function emptyLineString() {
  return { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} }
}

// ── DispatchAnimation ─────────────────────────────────────────────────────────

class DispatchAnimation {
  constructor(map, { srcGeo, dstGeo, droneCount, disasterColour, disasterType }) {
    this._map         = map
    this._src         = srcGeo        // { lat, lon }
    this._dst         = dstGeo        // { lat, lon }
    this._N           = droneCount
    this._colour      = disasterColour
    this._type        = disasterType

    this._rafId       = null
    this._completeCb  = null

    // Fixed-wing
    this._fwEl        = null
    this._fwMarker    = null
    this._orbitAngle  = 0
    this._fwTrailPts  = []

    // Dispatch arrow
    this._arrowEl     = null
    this._arrowMarker = null

    // Patrol drones — positions now driven by backend telemetry via DroneDotLayer
    this._patrolCenters  = []
    this._droneAngles    = []

    // Assessment panel
    this._assessPanel = null

    // Mapbox layer/source tracking for cleanup
    this._layerIds  = []
    this._sourceIds = []

    // Ellipse orbit radii (degrees)
    this._Rx = 0.0014
    this._Ry = 0.0014 * 0.7
  }

  onComplete(cb) { this._completeCb = cb }

  start() { this._phase1_travel() }

  stop() {
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null }

    for (const id of this._layerIds) {
      try { if (this._map.getLayer(id)) this._map.removeLayer(id) } catch (_) {}
    }
    for (const id of this._sourceIds) {
      try { if (this._map.getSource(id)) this._map.removeSource(id) } catch (_) {}
    }
    this._layerIds  = []
    this._sourceIds = []

    if (this._fwMarker)    { this._fwMarker.remove();    this._fwMarker    = null }
    if (this._arrowMarker) { this._arrowMarker.remove(); this._arrowMarker = null }

    if (this._assessPanel?.parentNode) {
      this._assessPanel.parentNode.removeChild(this._assessPanel)
      this._assessPanel = null
    }
  }

  // ── Internal helpers ───────────────────────────────────────────────────────

  _addSource(id, data) {
    if (!this._map.getSource(id)) {
      this._map.addSource(id, { type: 'geojson', data })
      this._sourceIds.push(id)
    }
  }

  _addLayer(def) {
    if (!this._map.getLayer(def.id)) {
      this._map.addLayer(def)
      this._layerIds.push(def.id)
    }
  }

  _removeLayerAndSource(layerId, sourceId) {
    try { if (this._map.getLayer(layerId))   this._map.removeLayer(layerId)   } catch (_) {}
    try { if (this._map.getSource(sourceId)) this._map.removeSource(sourceId) } catch (_) {}
    this._layerIds  = this._layerIds.filter(id => id !== layerId)
    this._sourceIds = this._sourceIds.filter(id => id !== sourceId)
  }

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

  _setFwTrail() {
    this._map.getSource('fw-trail-source')?.setData({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: this._fwTrailPts },
      properties: {},
    })
  }

  _advanceFwOrbit() {
    this._orbitAngle += 0.038
    const pt = this._orbitPoint(this._orbitAngle)
    if (this._fwMarker) this._fwMarker.setLngLat([pt.lon, pt.lat])
    if (this._fwEl)     this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(this._orbitAngle)}deg)`
    this._fwTrailPts.push([pt.lon, pt.lat])
    if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
    this._setFwTrail()
  }

  // ── Phase 1: Fixed-wing departs to orbit entry point ──────────────────────

  _phase1_travel() {
    const { angle: a0, pt: entry } = this._orbitEntry()
    this._orbitAngle = a0

    fireAgentEvent('ORCHESTRATOR', 'SURVEILLANCE_ACTIVE — Agent 1 dispatched · fixed-wing en route')

    this._addSource('fw-trail-source', emptyLineString())
    this._addLayer({
      id: 'fw-trail',
      type: 'line',
      source: 'fw-trail-source',
      paint: { 'line-color': this._colour, 'line-width': 1.5, 'line-dasharray': [4, 4], 'line-opacity': 0.45 },
    })

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, entry.lon, entry.lat) * 180 / Math.PI
    this._fwEl = document.createElement('div')
    this._fwEl.style.cssText = 'width:34px;height:32px;pointer-events:none;'
    this._fwEl.style.transform = `rotate(${bearingDeg}deg)`
    this._fwEl.innerHTML = fixedWingSVG(this._colour)
    this._fwMarker = new mapboxgl.Marker({ element: this._fwEl, anchor: 'center' })
      .setLngLat([this._src.lon, this._src.lat])
      .addTo(this._map)

    const animStart = performance.now()
    const srcLon = this._src.lon, srcLat = this._src.lat
    const dstLon = entry.lon,     dstLat = entry.lat

    const tick = (now) => {
      const t  = Math.min((now - animStart) / 2200, 1)
      const te = ease(t)
      const lon = srcLon + (dstLon - srcLon) * te
      const lat = srcLat + (dstLat - srcLat) * te

      this._fwMarker.setLngLat([lon, lat])
      this._fwTrailPts.push([lon, lat])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      this._setFwTrail()

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
      this._fwMarker.setLngLat([pt.lon, pt.lat])
      this._fwEl.style.transform = `rotate(${this._fwHeadingDeg(a)}deg)`

      this._fwTrailPts.push([pt.lon, pt.lat])
      if (this._fwTrailPts.length > 90) this._fwTrailPts.shift()
      this._setFwTrail()
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
      'z-index:10',
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

    // Agent 2 starts concurrently
    this._phase4_dispatch()

    // Hide after 2600ms; fw to 50% once panel gone
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

    this._addSource('dispatch-trail-source', emptyLineString())
    this._addLayer({
      id: 'dispatch-trail',
      type: 'line',
      source: 'dispatch-trail-source',
      paint: { 'line-color': this._colour, 'line-width': 1.5, 'line-dasharray': [4, 4], 'line-opacity': 0.45 },
    })

    const bearingDeg = calcBearing(this._src.lon, this._src.lat, this._dst.lon, this._dst.lat) * 180 / Math.PI
    this._arrowEl = document.createElement('div')
    this._arrowEl.style.cssText = 'width:14px;height:20px;pointer-events:none;'
    this._arrowEl.style.transform = `rotate(${bearingDeg}deg)`
    this._arrowEl.innerHTML = arrowSVG(this._colour)
    this._arrowMarker = new mapboxgl.Marker({ element: this._arrowEl, anchor: 'center' })
      .setLngLat([this._src.lon, this._src.lat])
      .addTo(this._map)

    const trailPts = []
    const animStart = performance.now()
    const srcLon = this._src.lon, srcLat = this._src.lat
    const dstLon = this._dst.lon, dstLat = this._dst.lat

    const tick = (now) => {
      const t  = Math.min((now - animStart) / 1900, 1)
      const te = ease(t)
      const lon = srcLon + (dstLon - srcLon) * te
      const lat = srcLat + (dstLat - srcLat) * te

      this._arrowMarker.setLngLat([lon, lat])
      trailPts.push([lon, lat])
      if (trailPts.length > 60) trailPts.shift()
      this._map.getSource('dispatch-trail-source')?.setData({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: trailPts },
        properties: {},
      })

      if (t < 1) {
        this._rafId = requestAnimationFrame(tick)
      } else {
        this._rafId = null
        this._phase5_burst()
      }
    }
    this._rafId = requestAnimationFrame(tick)
  }

  // ── Phase 5: Burst — arrow gone, rings expand ────────────────────────────

  _phase5_burst() {
    if (this._arrowMarker) { this._arrowMarker.remove(); this._arrowMarker = null }
    if (this._fwEl) this._fwEl.style.opacity = '0.4'

    fireAgentEvent('AGENT_2', 'Swarm on target — establishing patrol pattern')

    // Burst ring sources + layers
    const burstGeo = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [this._dst.lon, this._dst.lat] },
      properties: {},
    }
    this._addSource('dispatch-burst-source', burstGeo)
    this._addLayer({
      id: 'dispatch-burst-ring-1',
      type: 'circle',
      source: 'dispatch-burst-source',
      paint: { 'circle-radius': 0, 'circle-color': 'transparent', 'circle-stroke-width': 2, 'circle-stroke-color': this._colour, 'circle-stroke-opacity': 0.6 },
    })
    this._addLayer({
      id: 'dispatch-burst-ring-2',
      type: 'circle',
      source: 'dispatch-burst-source',
      paint: { 'circle-radius': 0, 'circle-color': 'transparent', 'circle-stroke-width': 1.5, 'circle-stroke-color': this._colour, 'circle-stroke-opacity': 0.6 },
    })

    const burstStart = performance.now()
    const animateBurst = (now) => {
      const elapsed = now - burstStart
      const t1 = Math.min(elapsed / 600, 1)
      try {
        this._map.setPaintProperty('dispatch-burst-ring-1', 'circle-radius', t1 * 80)
        this._map.setPaintProperty('dispatch-burst-ring-1', 'circle-stroke-opacity', 0.6 * (1 - t1))
      } catch (_) {}
      if (elapsed > 200) {
        const t2 = Math.min((elapsed - 200) / 900, 1)
        try {
          this._map.setPaintProperty('dispatch-burst-ring-2', 'circle-radius', t2 * 80)
          this._map.setPaintProperty('dispatch-burst-ring-2', 'circle-stroke-opacity', 0.6 * (1 - t2))
        } catch (_) {}
      }
      if (elapsed < 1200) {
        requestAnimationFrame(animateBurst)
      } else {
        this._removeLayerAndSource('dispatch-burst-ring-1', 'dispatch-burst-source')
        this._removeLayerAndSource('dispatch-burst-ring-2', 'dispatch-burst-source')
      }
    }
    requestAnimationFrame(animateBurst)

    // Compute patrol centres (used for reference only — drones appear via telemetry)
    for (let i = 0; i < this._N; i++) {
      const angle = (i / this._N) * 2 * Math.PI + (Math.random() - 0.5) * 0.4
      this._patrolCenters.push({
        lon: this._dst.lon + Math.cos(angle) * 0.0006,
        lat: this._dst.lat + Math.sin(angle) * 0.0006,
      })
      this._droneAngles.push(angle)
    }

    // Keep fw orbiting during burst, then move to patrol phase
    const moveStart = performance.now()
    const moveTick = (now) => {
      const t = Math.min((now - moveStart) / 800, 1)
      this._advanceFwOrbit()
      if (t < 1) {
        this._rafId = requestAnimationFrame(moveTick)
      } else {
        this._rafId = null
        this._phase6_patrol()
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
      this._rafId = requestAnimationFrame(tick)
    }
    this._rafId = requestAnimationFrame(tick)
  }
}

export default DispatchAnimation

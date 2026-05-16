import mapboxgl from 'mapbox-gl'
import { DISASTER_COLOR_MAP, SEVERITY_RADII } from './constants.js'

// Geographic circle as GeoJSON polygon
function circleGeoJSON(lat, lon, radiusM, steps = 64) {
  const coords = []
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    const dLon = (radiusM * Math.cos(angle)) / (111320 * Math.cos(lat * Math.PI / 180))
    const dLat = (radiusM * Math.sin(angle)) / 111320
    coords.push([lon + dLon, lat + dLat])
  }
  return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } }] }
}

class _MapStateManager {
  constructor() {
    this._map = null
    this._pendingUpdates = []
    this._flushInterval = null
    this._disasterMarkers = {}  // mapboxgl.Marker
    this._survivorMarkers = {}  // mapboxgl.Marker
    this._baseMarkers = {}      // mapboxgl.Marker for deployment bases
    this._riskSourceIds = {}    // {incident_id: ['sid0', 'sid1', 'sid2']}
    this._zoneSourceIds = {}    // {zoneId: 'sid'}
    this._droneManager = null
    this._incidentMeta = {}
    this._onIncidentAdd = null
  }

  init(mapInstance, droneManager, onIncidentAdd) {
    this._map = mapInstance
    this._droneManager = droneManager
    this._onIncidentAdd = onIncidentAdd
    this._flushInterval = setInterval(() => this._flush(), 1000)
  }

  destroy() {
    if (this._flushInterval) clearInterval(this._flushInterval)
    this._map = null
  }

  receive(event) {
    // Drone telemetry must be applied immediately — bypassing the 1s batch flush
    // gives smooth 10Hz position updates instead of choppy 1Hz jumps.
    if (event.action === 'update_drone') {
      if (this._droneManager && event.payload) this._droneManager.updateDrone(event.payload)
      return
    }
    this._pendingUpdates.push(event)
  }

  _flush() {
    if (!this._map || this._pendingUpdates.length === 0) return
    const updates = this._pendingUpdates.splice(0)
    for (const update of updates) {
      try { this._applyUpdate(update) } catch (e) {
        console.warn('[MapStateManager] update error', e, update)
      }
    }
  }

  _applyUpdate(event) {
    const { action, incident_id, payload } = event
    switch (action) {
      case 'add_marker':    this._addDisasterPin(incident_id, payload); break
      case 'update_marker': this._updateDisasterPin(incident_id, payload); break
      case 'remove_marker': this._removeDisasterPin(incident_id); break
      case 'add_zone':      this._addZoneCircle(payload); break
      case 'add_survivor':  this._addSurvivorPin(payload); break
      case 'update_drone':
        if (this._droneManager) this._droneManager.updateDrone(payload)
        break
      default: break
    }
  }

  _addDisasterPin(incident_id, payload) {
    if (this._disasterMarkers[incident_id]) { this._updateDisasterPin(incident_id, payload); return }
    const { lat, lon, type, severity, status } = payload
    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const iconPath = DISASTER_ICON_PATHS[type] || DISASTER_ICON_PATHS.fire

    // IncidentPin — pulsing ring + glowing core (from design system)
    const SIZE = 32
    const el = document.createElement('div')
    el.style.cssText = `position:relative;width:${SIZE}px;height:${SIZE}px;pointer-events:none`
    const ring = document.createElement('span')
    ring.style.cssText = `position:absolute;inset:0;border-radius:50%;border:1px solid ${color};animation:beaconRing 2s ease-out infinite`
    el.appendChild(ring)
    const ring2 = document.createElement('span')
    ring2.style.cssText = `position:absolute;inset:0;border-radius:50%;border:1px solid ${color};animation:beaconRing 2s ease-out infinite;animation-delay:0.7s`
    el.appendChild(ring2)
    const core = document.createElement('span')
    const cs = SIZE * 0.42
    core.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:${cs}px;height:${cs}px;border-radius:50%;background:${color};box-shadow:0 0 12px ${color},0 0 24px ${color}88`
    el.appendChild(core)
    const hl = document.createElement('span')
    const hs = SIZE * 0.18
    hl.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:${hs}px;height:${hs}px;border-radius:50%;background:rgba(255,255,255,0.9);box-shadow:0 0 4px rgba(255,255,255,0.9)`
    el.appendChild(hl)

    const timestamp = Date.now()
    this._incidentMeta[incident_id] = { type, severity, lat, lon, status: status || 'ACTIVE', timestamp }

    const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false, offset: [0, -44] })
    popup.on('open', () => {
      const meta = this._incidentMeta[incident_id]
      if (!meta) return
      const elapsed = Math.round((Date.now() - meta.timestamp) / 1000)
      const mins = Math.floor(elapsed / 60), secs = elapsed % 60
      const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
      popup.setHTML(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
        <div><span style="color:#7A8FA8">TYPE</span>  ${meta.type.toUpperCase().replace(/_/g, ' ')}</div>
        <div><span style="color:#7A8FA8">SEV </span>  ${meta.severity.toUpperCase()}</div>
        <div><span style="color:#7A8FA8">STAT</span>  ${meta.status}</div>
        <div><span style="color:#7A8FA8">T+  </span>  ${elapsedStr}</div>
      </div>`)
    })

    const marker = new mapboxgl.Marker(el, { anchor: 'bottom' })
      .setLngLat([lon, lat])
      .setPopup(popup)
      .addTo(this._map)

    this._disasterMarkers[incident_id] = marker
    this.addRiskZones(incident_id, lat, lon, type, severity)
    if (this._onIncidentAdd) this._onIncidentAdd(incident_id, this._incidentMeta[incident_id])
  }

  _updateDisasterPin(incident_id, payload) {
    const marker = this._disasterMarkers[incident_id]
    if (!marker) { this._addDisasterPin(incident_id, payload); return }
    const { lat, lon, status } = payload
    marker.setLngLat([lon, lat])
    if (this._incidentMeta[incident_id] && status) this._incidentMeta[incident_id].status = status
  }

  _removeDisasterPin(incident_id) {
    if (this._disasterMarkers[incident_id]) {
      this._disasterMarkers[incident_id].remove()
      delete this._disasterMarkers[incident_id]
    }
    this._removeRiskZones(incident_id)
    delete this._incidentMeta[incident_id]
  }

  addRiskZones(incident_id, lat, lon, type, severity) {
    if (!this._map || this._riskSourceIds[incident_id]) return
    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const radii = SEVERITY_RADII[severity.toUpperCase()] || SEVERITY_RADII.MEDIUM
    const zones = [
      { radius: radii.inner, fillOpacity: 0.25, stroke: true },
      { radius: radii.mid,   fillOpacity: 0.12, stroke: false },
      { radius: radii.outer, fillOpacity: 0.06, stroke: false },
    ]
    const sourceIds = []
    zones.forEach(({ radius, fillOpacity, stroke }, i) => {
      const sid = `riskzone-${incident_id}-${i}`
      this._map.addSource(sid, { type: 'geojson', data: circleGeoJSON(lat, lon, radius) })
      this._map.addLayer({ id: `${sid}-fill`, type: 'fill', source: sid, paint: { 'fill-color': color, 'fill-opacity': fillOpacity } })
      if (stroke) this._map.addLayer({ id: `${sid}-line`, type: 'line', source: sid, paint: { 'line-color': color, 'line-width': 1, 'line-opacity': 0.6 } })
      sourceIds.push(sid)
    })
    this._riskSourceIds[incident_id] = sourceIds
  }

  _removeRiskZones(incident_id) {
    if (!this._map) return
    for (const sid of (this._riskSourceIds[incident_id] || [])) {
      if (this._map.getLayer(`${sid}-fill`)) this._map.removeLayer(`${sid}-fill`)
      if (this._map.getLayer(`${sid}-line`)) this._map.removeLayer(`${sid}-line`)
      if (this._map.getSource(sid)) this._map.removeSource(sid)
    }
    delete this._riskSourceIds[incident_id]
  }

  _addZoneCircle(payload) {
    if (!this._map) return
    const { id, lat, lon, radius_m = 100, risk_level = 'medium' } = payload
    const zoneId = id || `zone-${lat?.toFixed(4)}-${lon?.toFixed(4)}`
    if (this._zoneSourceIds[zoneId]) return
    const COLOR = { critical: '#FF3B3B', high: '#FFB800', medium: '#FFE566', low: '#00FF88' }
    const color = COLOR[risk_level] || '#7A8FA8'
    const sid = `azone-${zoneId}`
    this._map.addSource(sid, { type: 'geojson', data: circleGeoJSON(lat, lon, radius_m) })
    this._map.addLayer({ id: `${sid}-line`, type: 'line', source: sid, paint: { 'line-color': color, 'line-width': 1.5, 'line-opacity': 0.75, 'line-dasharray': [6, 4] } })
    this._zoneSourceIds[zoneId] = sid
  }

  _addSurvivorPin(payload) {
    const { id, lat, lon, survivor_count, probability, detected_by, time } = payload
    if (this._survivorMarkers[id]) { this._survivorMarkers[id].setLngLat([lon, lat]); return }
    const el = document.createElement('div')
    el.className = 'survivor-pin'
    el.style.color = '#00FF88'
    const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false })
      .setHTML(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
        <div><span style="color:#7A8FA8">COUNT</span> ${survivor_count ?? '?'}</div>
        <div><span style="color:#7A8FA8">PROB </span> ${probability != null ? (probability * 100).toFixed(0) + '%' : '?'}</div>
        <div><span style="color:#7A8FA8">BY   </span> ${detected_by ?? '?'}</div>
        <div><span style="color:#7A8FA8">TIME </span> ${time ?? '?'}</div>
      </div>`)
    const marker = new mapboxgl.Marker(el, { anchor: 'center' })
      .setLngLat([lon, lat])
      .setPopup(popup)
      .addTo(this._map)
    this._survivorMarkers[id] = marker
  }

  renderBases(bases) {
    if (!this._map || !bases?.length) return
    bases.forEach((base) => {
      if (this._baseMarkers[base.id]) return
      const el = document.createElement('div')
      el.title = base.name
      el.style.cssText = `width:12px;height:12px;border-radius:2px;background:#90A4AE;border:1.5px solid rgba(255,255,255,0.5);cursor:pointer;box-sizing:border-box`
      const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false, offset: 8 })
        .setHTML(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#E8EDF5;min-width:140px">
          <div style="font-weight:600;margin-bottom:4px">${base.name}</div>
          <div style="color:#7A8FA8">${base.stocked_drone_types?.join(', ') || 'all types'}</div>
        </div>`)
      const m = new mapboxgl.Marker(el, { anchor: 'center' })
        .setLngLat([base.lon, base.lat])
        .setPopup(popup)
        .addTo(this._map)
      this._baseMarkers[base.id] = m
    })
  }

  startFireSuppression(incident_id, dur, sev) {
    if (!this._map) return
    const meta = this._incidentMeta[incident_id]
    if (!meta) return
    const { lat, lon } = meta
    const origSev = meta.severity || sev || 'medium'
    const radii = SEVERITY_RADII[origSev.toUpperCase()] || SEVERITY_RADII.MEDIUM
    const zoneRadiiBase = [radii.inner, radii.mid, radii.outer]

    if (sev === 'low') {
      setTimeout(() => this._removeRiskZones(incident_id), dur)
    } else if (sev === 'medium') {
      setTimeout(() => {
        const sids = this._riskSourceIds[incident_id]
        if (!sids || !this._map) return
        sids.forEach((sid, i) => {
          const src = this._map.getSource(sid)
          if (src) src.setData(circleGeoJSON(lat, lon, zoneRadiiBase[i] * 0.25))
        })
      }, dur / 2)
      setTimeout(() => this._removeRiskZones(incident_id), dur)
    } else {
      // high / critical — shrink to 45% + recolor amber (contained, not extinguished)
      const amber = '#FFB800'
      setTimeout(() => {
        const sids = this._riskSourceIds[incident_id]
        if (!sids || !this._map) return
        sids.forEach((sid, i) => {
          const src = this._map.getSource(sid)
          if (src) src.setData(circleGeoJSON(lat, lon, zoneRadiiBase[i] * 0.45))
          if (this._map.getLayer(`${sid}-fill`)) this._map.setPaintProperty(`${sid}-fill`, 'fill-color', amber)
          if (this._map.getLayer(`${sid}-line`)) this._map.setPaintProperty(`${sid}-line`, 'line-color', amber)
        })
      }, dur / 2)
    }
  }

  triggerSuppressionDrop(lat, lon) {
    if (!this._map) return
    const uid = `spray-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    this._map.addSource(uid, { type: 'geojson', data: circleGeoJSON(lat, lon, 12) })
    this._map.addLayer({ id: `${uid}-fill`, type: 'fill', source: uid, paint: { 'fill-color': '#00BFFF', 'fill-opacity': 0.65 } })
    this._map.addLayer({ id: `${uid}-line`, type: 'line', source: uid, paint: { 'line-color': '#00BFFF', 'line-width': 1.5, 'line-opacity': 0.9 } })
    setTimeout(() => {
      if (!this._map) return
      if (this._map.getLayer(`${uid}-fill`)) this._map.removeLayer(`${uid}-fill`)
      if (this._map.getLayer(`${uid}-line`)) this._map.removeLayer(`${uid}-line`)
      if (this._map.getSource(uid)) this._map.removeSource(uid)
    }, 2000)
  }

  getActiveIncidentColor() {
    const ids = Object.keys(this._incidentMeta)
    if (ids.length === 0) return '#00FF88'
    return DISASTER_COLOR_MAP[this._incidentMeta[ids[0]].type] || '#00FF88'
  }

  getActiveIncidents() { return { ...this._incidentMeta } }
}

const MapStateManager = new _MapStateManager()
export default MapStateManager

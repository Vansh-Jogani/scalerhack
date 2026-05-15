import L from 'leaflet'
import { DISASTER_COLOR_MAP, SEVERITY_RADII, DISASTER_ICON_PATHS } from './constants.js'

class _MapStateManager {
  constructor() {
    this._map = null
    this._pendingUpdates = []
    this._flushInterval = null
    this._disasterMarkers = {}
    this._survivorMarkers = {}
    this._riskLayers = {}
    this._zoneLayers = {}
    this._evacLayers = {}
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
      case 'add_marker': this._addDisasterPin(incident_id, payload); break
      case 'update_marker': this._updateDisasterPin(incident_id, payload); break
      case 'remove_marker': this._removeDisasterPin(incident_id); break
      case 'add_zone': this._addZoneCircle(payload); break
      case 'add_survivor': this._addSurvivorPin(payload); break
      case 'update_drone':
        if (this._droneManager) this._droneManager.updateDrone(payload)
        break
      default: break
    }
  }

  _addDisasterPin(incident_id, payload) {
    if (this._disasterMarkers[incident_id]) {
      this._updateDisasterPin(incident_id, payload)
      return
    }
    const { lat, lon, type, severity, status } = payload
    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const iconPath = DISASTER_ICON_PATHS[type] || DISASTER_ICON_PATHS.fire

    const html = `
      <div class="disaster-pin" style="color:${color}">
        <svg viewBox="0 0 36 44" xmlns="http://www.w3.org/2000/svg">
          <path d="M18 2C10.3 2 4 8.3 4 16c0 10 14 26 14 26S32 26 32 16C32 8.3 25.7 2 18 2z" fill="${color}"/>
          <svg x="6" y="4" width="24" height="24" viewBox="0 0 24 24">${iconPath}</svg>
        </svg>
      </div>
    `
    const icon = L.divIcon({ className: '', html, iconSize: [36, 44], iconAnchor: [18, 44] })
    const marker = L.marker([lat, lon], { icon }).addTo(this._map)

    const timestamp = Date.now()
    this._incidentMeta[incident_id] = { type, severity, lat, lon, status: status || 'ACTIVE', timestamp }

    marker.bindPopup(() => {
      const meta = this._incidentMeta[incident_id]
      if (!meta) return ''
      const elapsed = Math.round((Date.now() - meta.timestamp) / 1000)
      const mins = Math.floor(elapsed / 60)
      const secs = elapsed % 60
      const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
      return `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
        <div><span style="color:#7A8FA8">TYPE</span>  ${meta.type.toUpperCase().replace('_', ' ')}</div>
        <div><span style="color:#7A8FA8">SEV </span>  ${meta.severity.toUpperCase()}</div>
        <div><span style="color:#7A8FA8">STAT</span>  ${meta.status}</div>
        <div><span style="color:#7A8FA8">T+  </span>  ${elapsedStr}</div>
      </div>`
    }, { className: 'aria-popup' })

    this._disasterMarkers[incident_id] = marker
    this.addRiskZones(incident_id, lat, lon, type, severity)
    if (this._onIncidentAdd) this._onIncidentAdd(incident_id, this._incidentMeta[incident_id])
  }

  _updateDisasterPin(incident_id, payload) {
    const marker = this._disasterMarkers[incident_id]
    if (!marker) { this._addDisasterPin(incident_id, payload); return }
    const { lat, lon, status } = payload
    marker.setLatLng([lat, lon])
    if (this._incidentMeta[incident_id]) {
      this._incidentMeta[incident_id].status = status || this._incidentMeta[incident_id].status
    }
  }

  _removeDisasterPin(incident_id) {
    if (this._disasterMarkers[incident_id]) {
      this._map.removeLayer(this._disasterMarkers[incident_id])
      delete this._disasterMarkers[incident_id]
    }
    this._removeRiskZones(incident_id)
    delete this._incidentMeta[incident_id]
  }

  addRiskZones(incident_id, lat, lon, type, severity) {
    if (!this._map) return
    if (this._riskLayers[incident_id]) return
    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const radii = SEVERITY_RADII[severity.toUpperCase()] || SEVERITY_RADII.MEDIUM
    const zones = [
      { radius: radii.inner, opacity: 0.25, stroke: true },
      { radius: radii.mid, opacity: 0.12, stroke: false },
      { radius: radii.outer, opacity: 0.06, stroke: false },
    ]
    const layers = []
    zones.forEach(({ radius, opacity, stroke }) => {
      const circle = L.circle([lat, lon], {
        radius,
        fillColor: color,
        fillOpacity: opacity,
        color: stroke ? color : 'transparent',
        weight: stroke ? 1 : 0,
        opacity: 0.6,
      }).addTo(this._map)
      layers.push(circle)
    })
    this._riskLayers[incident_id] = layers
  }

  _removeRiskZones(incident_id) {
    if (!this._map) return
    const layers = this._riskLayers[incident_id] || []
    layers.forEach((l) => this._map.removeLayer(l))
    delete this._riskLayers[incident_id]
  }

  _addZoneCircle(payload) {
    if (!this._map) return
    const { id, lat, lon, radius_m = 100, risk_level = 'medium' } = payload
    const zoneId = id || `zone-${lat?.toFixed(4)}-${lon?.toFixed(4)}`
    if (this._zoneLayers[zoneId]) return

    const COLOR = { critical: '#FF3B3B', high: '#FFB800', medium: '#FFE566', low: '#00FF88' }
    const color = COLOR[risk_level] || '#7A8FA8'

    const circle = L.circle([lat, lon], {
      radius: radius_m,
      color,
      fillColor: 'transparent',
      weight: 1.5,
      opacity: 0.75,
      dashArray: '6 4',
    }).addTo(this._map)
    this._zoneLayers[zoneId] = circle
  }

  _addSurvivorPin(payload) {
    const { id, lat, lon, survivor_count, probability, detected_by, time } = payload
    if (this._survivorMarkers[id]) {
      this._survivorMarkers[id].setLatLng([lat, lon])
      return
    }
    const icon = L.divIcon({
      className: '',
      html: '<div class="survivor-pin" style="color:#00FF88"></div>',
      iconSize: [14, 14], iconAnchor: [7, 7],
    })
    const marker = L.marker([lat, lon], { icon }).addTo(this._map)
    marker.bindPopup(`
      <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
        <div><span style="color:#7A8FA8">COUNT</span> ${survivor_count ?? '?'}</div>
        <div><span style="color:#7A8FA8">PROB </span> ${probability != null ? (probability * 100).toFixed(0) + '%' : '?'}</div>
        <div><span style="color:#7A8FA8">BY   </span> ${detected_by ?? '?'}</div>
        <div><span style="color:#7A8FA8">TIME </span> ${time ?? '?'}</div>
      </div>
    `, { className: 'aria-popup' })
    this._survivorMarkers[id] = marker
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

import mapboxgl from 'mapbox-gl'
import { DISASTER_COLOR_MAP, SEVERITY_RADII, DISASTER_ICON_PATHS } from './constants.js'

// Converts metres to approximate degrees latitude (for circle approximation)
function metresToDeg(metres) {
  return metres / 111320
}

// Builds a GeoJSON circle polygon around a lng/lat point
function circleGeoJSON(lon, lat, radiusM, steps = 64) {
  const r = metresToDeg(radiusM)
  const coords = []
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    coords.push([lon + r * Math.cos(angle), lat + r * Math.sin(angle)])
  }
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: {},
  }
}

class _MapStateManager {
  constructor() {
    this._map = null
    this._pendingUpdates = []
    this._flushInterval = null
    this._disasterMarkers = {}   // incident_id → mapboxgl.Marker
    this._survivorMarkers = {}   // id → mapboxgl.Marker
    this._riskLayers = {}        // incident_id → [layerIds]
    this._evacLayers = {}        // incident_id → sourceId
    this._droneManager = null
    this._incidentMeta = {}      // incident_id → { type, severity, lat, lon, timestamp }
    this._onIncidentAdd = null   // callback(incident_id, meta)
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
      try {
        this._applyUpdate(update)
      } catch (e) {
        console.warn('[MapStateManager] update error', e, update)
      }
    }
  }

  _applyUpdate(event) {
    const { action, incident_id, payload } = event

    switch (action) {
      case 'add_marker':
        this._addDisasterPin(incident_id, payload)
        break
      case 'update_marker':
        this._updateDisasterPin(incident_id, payload)
        break
      case 'remove_marker':
        this._removeDisasterPin(incident_id)
        break
      case 'update_layer':
        this._updateLayer(payload)
        break
      case 'add_survivor':
        this._addSurvivorPin(payload)
        break
      case 'update_drone':
        if (this._droneManager) this._droneManager.updateDrone(payload)
        break
      default:
        console.warn('[MapStateManager] unknown action', action)
    }
  }

  // ── Disaster pins ──────────────────────────────────────────────────

  _addDisasterPin(incident_id, payload) {
    if (this._disasterMarkers[incident_id]) {
      this._updateDisasterPin(incident_id, payload)
      return
    }
    const { lat, lon, type, severity, status } = payload
    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const iconPath = DISASTER_ICON_PATHS[type] || DISASTER_ICON_PATHS.fire

    const el = document.createElement('div')
    el.className = 'disaster-pin'
    el.style.color = color
    el.innerHTML = `
      <svg viewBox="0 0 36 44" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="shadow-${incident_id}">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="${color}" flood-opacity="0.6"/>
          </filter>
        </defs>
        <path d="M18 2C10.3 2 4 8.3 4 16c0 10 14 26 14 26S32 26 32 16C32 8.3 25.7 2 18 2z"
              fill="${color}" filter="url(#shadow-${incident_id})"/>
        <svg x="6" y="4" width="24" height="24" viewBox="0 0 24 24">
          ${iconPath}
        </svg>
      </svg>
    `

    const timestamp = Date.now()
    this._incidentMeta[incident_id] = { type, severity, lat, lon, status: status || 'ACTIVE', timestamp }

    el.addEventListener('click', (e) => {
      e.stopPropagation()
      this._showIncidentPopup(incident_id, lat, lon)
    })

    const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom' })
      .setLngLat([lon, lat])
      .addTo(this._map)

    this._disasterMarkers[incident_id] = marker

    // Add risk zones immediately
    this.addRiskZones(incident_id, lat, lon, type, severity)

    if (this._onIncidentAdd) this._onIncidentAdd(incident_id, this._incidentMeta[incident_id])
  }

  _updateDisasterPin(incident_id, payload) {
    const marker = this._disasterMarkers[incident_id]
    if (!marker) {
      this._addDisasterPin(incident_id, payload)
      return
    }
    const { lat, lon, status } = payload
    marker.setLngLat([lon, lat])
    if (this._incidentMeta[incident_id]) {
      this._incidentMeta[incident_id].status = status || this._incidentMeta[incident_id].status
    }
  }

  _removeDisasterPin(incident_id) {
    if (this._disasterMarkers[incident_id]) {
      this._disasterMarkers[incident_id].remove()
      delete this._disasterMarkers[incident_id]
    }
    this._removeRiskZones(incident_id)
    delete this._incidentMeta[incident_id]
  }

  _showIncidentPopup(incident_id, lat, lon) {
    const meta = this._incidentMeta[incident_id]
    if (!meta) return
    const elapsed = Math.round((Date.now() - meta.timestamp) / 1000)
    const mins = Math.floor(elapsed / 60)
    const secs = elapsed % 60
    const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
    new mapboxgl.Popup({ closeButton: true, maxWidth: '220px' })
      .setLngLat([lon, lat])
      .setHTML(`
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
          <div><span style="color:#7A8FA8">TYPE</span>  ${meta.type.toUpperCase().replace('_', ' ')}</div>
          <div><span style="color:#7A8FA8">SEV </span>  ${meta.severity.toUpperCase()}</div>
          <div><span style="color:#7A8FA8">STAT</span>  ${meta.status}</div>
          <div><span style="color:#7A8FA8">T+  </span>  ${elapsedStr}</div>
        </div>
      `)
      .addTo(this._map)
  }

  // ── Risk zone rings ────────────────────────────────────────────────

  addRiskZones(incident_id, lat, lon, type, severity) {
    if (!this._map || !this._map.loaded()) return
    if (this._riskLayers[incident_id]) return

    const color = DISASTER_COLOR_MAP[type] || '#FF4500'
    const radii = SEVERITY_RADII[severity.toUpperCase()] || SEVERITY_RADII.MEDIUM
    const zones = [
      { key: 'critical', radius: radii.inner, opacity: 0.25, stroke: true },
      { key: 'high',     radius: radii.mid,   opacity: 0.12, stroke: false },
      { key: 'medium',   radius: radii.outer,  opacity: 0.06, stroke: false },
    ]

    const layerIds = []
    zones.forEach(({ key, radius, opacity, stroke }) => {
      const sourceId = `risk-${key}-${incident_id}`
      const layerId = sourceId

      if (!this._map.getSource(sourceId)) {
        this._map.addSource(sourceId, {
          type: 'geojson',
          data: circleGeoJSON(lon, lat, radius),
        })
      }
      if (!this._map.getLayer(layerId)) {
        this._map.addLayer({
          id: layerId,
          type: 'fill',
          source: sourceId,
          paint: {
            'fill-color': color,
            'fill-opacity': opacity,
          },
        })
        layerIds.push(layerId)
      }
      if (stroke) {
        const strokeId = `${layerId}-stroke`
        if (!this._map.getLayer(strokeId)) {
          this._map.addLayer({
            id: strokeId,
            type: 'line',
            source: sourceId,
            paint: {
              'line-color': color,
              'line-opacity': 0.6,
              'line-width': 1,
            },
          })
          layerIds.push(strokeId)
        }
      }
    })

    this._riskLayers[incident_id] = layerIds
  }

  _removeRiskZones(incident_id) {
    if (!this._map) return
    const layers = this._riskLayers[incident_id] || []
    layers.forEach((id) => {
      if (this._map.getLayer(id)) this._map.removeLayer(id)
      if (this._map.getSource(id)) this._map.removeSource(id)
    })
    delete this._riskLayers[incident_id]
  }

  // ── Evacuation routes ──────────────────────────────────────────────

  addEvacRoute(incident_id, coordinates) {
    if (!this._map) return
    const sourceId = `evac-route-${incident_id}`
    const layerId = sourceId

    const geojson = {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates },
      properties: {},
    }

    if (this._map.getSource(sourceId)) {
      this._map.getSource(sourceId).setData(geojson)
    } else {
      this._map.addSource(sourceId, { type: 'geojson', data: geojson })
      this._map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        paint: {
          'line-color': '#00FF88',
          'line-width': 3,
          'line-opacity': 0.8,
          'line-dasharray': [4, 4],
        },
      })
      this._evacLayers[incident_id] = sourceId
    }
  }

  // ── Survivor pins ──────────────────────────────────────────────────

  _addSurvivorPin(payload) {
    const { id, lat, lon, survivor_count, probability, detected_by, time } = payload
    if (this._survivorMarkers[id]) {
      this._survivorMarkers[id].setLngLat([lon, lat])
      return
    }

    const el = document.createElement('div')
    el.className = 'survivor-pin'
    el.style.color = '#00FF88'

    el.addEventListener('click', (e) => {
      e.stopPropagation()
      new mapboxgl.Popup({ closeButton: true, maxWidth: '200px' })
        .setLngLat([lon, lat])
        .setHTML(`
          <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8">
            <div><span style="color:#7A8FA8">COUNT</span> ${survivor_count ?? '?'}</div>
            <div><span style="color:#7A8FA8">PROB </span> ${probability != null ? (probability * 100).toFixed(0) + '%' : '?'}</div>
            <div><span style="color:#7A8FA8">BY   </span> ${detected_by ?? '?'}</div>
            <div><span style="color:#7A8FA8">TIME </span> ${time ?? '?'}</div>
          </div>
        `)
        .addTo(this._map)
    })

    this._survivorMarkers[id] = new mapboxgl.Marker({ element: el })
      .setLngLat([lon, lat])
      .addTo(this._map)
  }

  // ── Generic layer update ───────────────────────────────────────────

  _updateLayer(payload) {
    const { source_id, geojson } = payload
    if (!source_id || !this._map) return
    const source = this._map.getSource(source_id)
    if (source) source.setData(geojson)
  }

  // ── Public helpers ─────────────────────────────────────────────────

  getActiveIncidentColor() {
    const ids = Object.keys(this._incidentMeta)
    if (ids.length === 0) return '#00FF88'
    const meta = this._incidentMeta[ids[0]]
    return DISASTER_COLOR_MAP[meta.type] || '#00FF88'
  }

  getActiveIncidents() {
    return { ...this._incidentMeta }
  }
}

const MapStateManager = new _MapStateManager()
export default MapStateManager

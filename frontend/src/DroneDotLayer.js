/**
 * DroneDotLayer — replaces DroneManager.js
 *
 * Manages a single Mapbox GeoJSON source ('drones-source') and renders all
 * drones as circle + label layers. No HTML markers, no rAF lerp loop.
 * Position updates are instant via source.setData() — Mapbox handles GPU rendering.
 */

import mapboxgl from 'mapbox-gl'
import { DRONE_STATES } from './constants.js'

// Fallback color for unknown states
const FALLBACK_COLOR = '#7A8FA8'

class _DroneDotLayer {
  constructor() {
    this._map = null
    /** @type {Map<string, object>} drone_id → GeoJSON Feature */
    this._features = new Map()
    this._popupRef = null
  }

  /**
   * Initialize sources and layers on the map.
   * Must be called after map 'load' event.
   * @param {mapboxgl.Map} map
   */
  init(map) {
    this._map = map

    map.addSource('drones-source', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })

    // Circle dot layer
    map.addLayer({
      id: 'drones-dot',
      type: 'circle',
      source: 'drones-source',
      paint: {
        'circle-radius': [
          'match', ['get', 'state'],
          'THERMAL_SCAN', 9,
          'LOITERING',    8,
          7,
        ],
        'circle-color': ['get', 'dot_color'],
        'circle-opacity': 0.92,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-opacity': 0.4,
        'circle-blur': [
          'match', ['get', 'state'],
          'THERMAL_SCAN', 0.3,
          0,
        ],
      },
    })

    // Label layer — only visible at zoom >= 13
    map.addLayer({
      id: 'drones-label',
      type: 'symbol',
      source: 'drones-source',
      minzoom: 13,
      layout: {
        'text-field': ['get', 'drone_id'],
        'text-size': 9,
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
        'text-font': ['DIN Offc Pro Regular', 'Arial Unicode MS Regular'],
      },
      paint: {
        'text-color': '#E8EDF5',
        'text-halo-color': '#0A0E14',
        'text-halo-width': 1,
      },
    })

    // Click popup
    map.on('click', 'drones-dot', (e) => {
      if (!e.features?.length) return
      const props = e.features[0].properties
      const coords = e.features[0].geometry.coordinates

      if (this._popupRef) { this._popupRef.remove(); this._popupRef = null }

      // Escape values to avoid XSS from untrusted content
      const safe = (v) => String(v ?? '?').replace(/</g, '&lt;').replace(/>/g, '&gt;')

      this._popupRef = new mapboxgl.Popup({ closeButton: true, maxWidth: '200px' })
        .setLngLat(coords)
        .setHTML(`
          <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8;color:#E8EDF5">
            <div><span style="color:#7A8FA8">ID   </span> ${safe(props.drone_id)}</div>
            <div><span style="color:#7A8FA8">STATE</span> ${safe(props.state)}</div>
            <div><span style="color:#7A8FA8">BAT  </span> ${props.battery_pct != null ? Number(props.battery_pct).toFixed(0) + '%' : '?'}</div>
            <div><span style="color:#7A8FA8">ALT  </span> ${props.alt != null ? Number(props.alt).toFixed(0) + 'm' : '?'}</div>
            <div><span style="color:#7A8FA8">SPD  </span> ${props.speed != null ? Number(props.speed).toFixed(1) + ' m/s' : '?'}</div>
          </div>
        `)
        .addTo(map)
    })

    map.on('mouseenter', 'drones-dot', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'drones-dot', () => {
      map.getCanvas().style.cursor = ''
    })
  }

  /**
   * Upsert a drone's position and state, then push updated FeatureCollection.
   * @param {{ drone_id: string, lat: number, lon: number, state: string,
   *           battery_pct?: number, alt?: number, speed?: number }} data
   */
  updateDrone(data) {
    if (!this._map) return
    const { drone_id, lat, lon, state, battery_pct, alt, speed } = data

    const dot_color = DRONE_STATES[state] ?? FALLBACK_COLOR

    this._features.set(drone_id, {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: {
        drone_id,
        state: state || 'IDLE',
        dot_color,
        battery_pct: battery_pct ?? 0,
        alt: alt ?? 0,
        speed: speed ?? 0,
      },
    })

    const source = this._map.getSource('drones-source')
    if (source) {
      source.setData({
        type: 'FeatureCollection',
        features: Array.from(this._features.values()),
      })
    }
  }

  /**
   * Remove all layers and source from the map. Call on component unmount.
   */
  destroy() {
    if (this._popupRef) { this._popupRef.remove(); this._popupRef = null }
    if (!this._map) return
    try { if (this._map.getLayer('drones-label')) this._map.removeLayer('drones-label') } catch (_) {}
    try { if (this._map.getLayer('drones-dot'))   this._map.removeLayer('drones-dot')   } catch (_) {}
    try { if (this._map.getSource('drones-source')) this._map.removeSource('drones-source') } catch (_) {}
    this._features.clear()
    this._map = null
  }
}

const DroneDotLayer = new _DroneDotLayer()
export default DroneDotLayer

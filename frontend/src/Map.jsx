import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapStateManager from './MapStateManager.js'
import DroneDotLayer from './DroneDotLayer.js'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_COLOR_MAP, MAX_ZONE_RADIUS_M } from './constants.js'
import responseCentres from './data/response_centres.json'
import DispatchAnimation, { findNearestCentre } from './DispatchAnimation.js'

export { responseCentres }

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN

const MAP_CENTER = [78.4867, 17.3850]
const MAP_ZOOM = 12

// ─── Circle helpers ───────────────────────────────────────────────────────────

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function circleGeoJSON(centerLng, centerLat, radiusM, steps = 64) {
  const rLat = radiusM / 111320
  const rLng = radiusM / (111320 * Math.cos(centerLat * Math.PI / 180))
  const coords = []
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    coords.push([centerLng + rLng * Math.cos(angle), centerLat + rLat * Math.sin(angle)])
  }
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: {},
  }
}

// ─── Module-level draw state (shared with AdminPanel via named exports) ───────

let _drawColor = '#FF4500'
let _drawMapRef = null
let _centerMarker = null   // mapboxgl.Marker dot at circle centre
let _circleCenter = null   // [lng, lat] or null
let _dispatchAnim = null   // active DispatchAnimation instance

function _onIncidentAdd(incident_id, meta) {
  if (!_drawMapRef) return
  if (_dispatchAnim) _dispatchAnim.stop()
  const nearest = findNearestCentre([[meta.lon, meta.lat]], responseCentres)
  if (!nearest) return
  const colour = DISASTER_COLOR_MAP[meta.type] || '#FF4500'
  _dispatchAnim = new DispatchAnimation(_drawMapRef, {
    srcGeo: { lat: nearest.lat, lon: nearest.lon },
    dstGeo: { lat: meta.lat, lon: meta.lon },
    droneCount: 3,
    disasterColour: colour,
    disasterType: meta.type,
  })
  _dispatchAnim.start()
}

/** Called by AdminPanel when disaster type changes — updates circle colour live. */
export function setDrawColor(color) {
  _drawColor = color
  if (_drawMapRef) {
    if (_drawMapRef.getLayer('draw-circle-fill'))
      _drawMapRef.setPaintProperty('draw-circle-fill', 'fill-color', color)
    if (_drawMapRef.getLayer('draw-circle-outline'))
      _drawMapRef.setPaintProperty('draw-circle-outline', 'line-color', color)
  }
  if (_centerMarker)
    _centerMarker.getElement().style.borderColor = color
}

/** Called by AdminPanel CLEAR button — removes circle and centre marker. */
export function clearDrawPolygon() {
  if (_centerMarker) { _centerMarker.remove(); _centerMarker = null }
  _circleCenter = null
  if (_drawMapRef?.getSource('draw-circle-source')) {
    _drawMapRef.getSource('draw-circle-source').setData({ type: 'FeatureCollection', features: [] })
  }
}

// ─────────────────────────────────────────────────────────────────────────────

function IncidentBadges({ incidents }) {
  const typeCounts = {}
  Object.values(incidents).forEach(({ type }) => {
    const key = type.toUpperCase().replace(/ /g, '_')
    typeCounts[key] = (typeCounts[key] || 0) + 1
  })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
      {Object.entries(typeCounts).map(([type, count]) => {
        const color = DISASTER_COLORS[type] || '#E8EDF5'
        const label = DISASTER_LABELS[type] || type
        return (
          <div key={type} className="incident-badge" style={{ color, borderColor: color }}>
            <span>{count}</span>
            <span>{label}</span>
          </div>
        )
      })}
    </div>
  )
}

function Map({ isSelectingLocation, onLocationSelect, incidents, systemStatus }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const [coords, setCoords] = useState({ lat: 0, lon: 0 })
  const selectingRef = useRef(isSelectingLocation)

  // Sync cursor; clear draw state whenever draw mode starts fresh
  useEffect(() => {
    selectingRef.current = isSelectingLocation
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = isSelectingLocation ? 'crosshair' : ''
    }
    if (isSelectingLocation) {
      if (_centerMarker) { _centerMarker.remove(); _centerMarker = null }
      _circleCenter = null
      if (_drawMapRef?.getSource('draw-circle-source')) {
        _drawMapRef.getSource('draw-circle-source').setData({ type: 'FeatureCollection', features: [] })
      }
    }
  }, [isSelectingLocation])

  // Map initialisation
  useEffect(() => {
    if (mapRef.current) return
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      attributionControl: false,
    })
    mapRef.current = map

    map.addControl(new mapboxgl.AttributionControl({ compact: true }), 'bottom-right')

    map.on('load', () => {
      _drawMapRef = map

      // Circle draw sources / layers
      map.addSource('draw-circle-source', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'draw-circle-fill',
        type: 'fill',
        source: 'draw-circle-source',
        paint: { 'fill-color': _drawColor, 'fill-opacity': 0.15 },
      })
      map.addLayer({
        id: 'draw-circle-outline',
        type: 'line',
        source: 'draw-circle-source',
        paint: { 'line-color': _drawColor, 'line-width': 2, 'line-dasharray': [5, 3] },
      })

      // ── Response centres ──
      const TYPE_COLOUR_EXPRESSION = [
        'match', ['get', 'type'],
        'FIRE_STATION',        '#4FC3F7',
        'NDRF',                '#1565C0',
        'SDRF',                '#1E88E5',
        'HOSPITAL',            '#E53935',
        'POLICE',              '#5E35B1',
        'CIVIL_DEFENCE',       '#00897B',
        'AIRPORT_EMERGENCY',   '#F4511E',
        'MUNICIPAL_EMERGENCY', '#039BE5',
        '#4FC3F7',
      ]

      map.addSource('response-centres', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: responseCentres.map((rc) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [rc.lon, rc.lat] },
            properties: {
              id: rc.id,
              name: rc.name,
              type: rc.type,
              address: rc.address,
              verified: rc.verified,
            },
          })),
        },
      })

      map.addLayer({
        id: 'response-centres-ring',
        type: 'circle',
        source: 'response-centres',
        paint: {
          'circle-radius': 10,
          'circle-color': 'transparent',
          'circle-stroke-width': 1,
          'circle-stroke-color': TYPE_COLOUR_EXPRESSION,
          'circle-stroke-opacity': ['case', ['get', 'verified'], 0.5, 0.25],
        },
      })

      map.addLayer({
        id: 'response-centres-dot',
        type: 'circle',
        source: 'response-centres',
        paint: {
          'circle-radius': 5,
          'circle-color': TYPE_COLOUR_EXPRESSION,
          'circle-opacity': ['case', ['get', 'verified'], 0.9, 0.5],
          'circle-stroke-width': 0.5,
          'circle-stroke-color': 'white',
        },
      })

      map.addLayer({
        id: 'response-centres-label',
        type: 'symbol',
        source: 'response-centres',
        minzoom: 13,
        layout: {
          'text-field': ['get', 'name'],
          'text-size': 10,
          'text-offset': [0, 1.2],
          'text-anchor': 'top',
          'text-font': ['DIN Offc Pro Regular', 'Arial Unicode MS Regular'],
        },
        paint: {
          'text-color': '#E8EDF5',
          'text-halo-color': '#0A0E14',
          'text-halo-width': 1,
        },
      })

      map.on('click', 'response-centres-dot', (e) => {
        if (selectingRef.current) return
        const props = e.features[0].properties
        new mapboxgl.Popup({ className: 'aria-popup' })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div style="font-family:JetBrains Mono,monospace;font-size:11px;color:#E8EDF5;background:#111822;padding:8px 10px;border-radius:6px;min-width:160px">
              <div style="font-weight:600;margin-bottom:4px">${props.name}</div>
              <div style="color:#7A8FA8">${props.type.replace(/_/g,' ')}</div>
              <div style="color:#7A8FA8;margin-top:2px">${props.address}</div>
              ${!props.verified ? '<div style="color:#FFB800;margin-top:4px">coords approximate</div>' : ''}
            </div>
          `)
          .addTo(map)
      })
      map.on('mouseenter', 'response-centres-dot', () => {
        if (!selectingRef.current) map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'response-centres-dot', () => {
        map.getCanvas().style.cursor = selectingRef.current ? 'crosshair' : ''
      })

      MapStateManager.init(map, DroneDotLayer, _onIncidentAdd)
      DroneDotLayer.init(map)
    })

    // Coordinate readout
    map.on('mousemove', (e) => {
      setCoords({ lat: e.lngLat.lat, lon: e.lngLat.lng })

      // Live circle preview after centre is placed (capped at MAX_ZONE_RADIUS_M)
      if (selectingRef.current && _circleCenter) {
        const raw = haversineM(_circleCenter[1], _circleCenter[0], e.lngLat.lat, e.lngLat.lng)
        const radiusM = Math.min(raw, MAX_ZONE_RADIUS_M)
        if (radiusM >= 20) {
          const src = _drawMapRef?.getSource('draw-circle-source')
          if (src) src.setData(circleGeoJSON(_circleCenter[0], _circleCenter[1], radiusM))
        }
      }
    })

    map.on('click', (e) => {
      if (!selectingRef.current) return
      const { lng, lat } = e.lngLat

      if (!_circleCenter) {
        // ── Click 1: place centre ──
        _circleCenter = [lng, lat]

        const el = document.createElement('div')
        el.style.cssText = [
          'width:10px', 'height:10px', 'border-radius:50%',
          'background:white', `border:2px solid ${_drawColor}`,
          'box-sizing:border-box', 'pointer-events:none',
        ].join(';')
        _centerMarker = new mapboxgl.Marker({ element: el, anchor: 'center' })
          .setLngLat([lng, lat])
          .addTo(map)
      } else {
        // ── Click 2: fix radius, close (capped at MAX_ZONE_RADIUS_M) ──
        const radiusM = Math.min(
          haversineM(_circleCenter[1], _circleCenter[0], lat, lng),
          MAX_ZONE_RADIUS_M,
        )
        if (radiusM < 20) return // ignore accidental near-centre click

        const geoJSON = circleGeoJSON(_circleCenter[0], _circleCenter[1], radiusM)
        // Persist the final circle on the map
        const src = _drawMapRef?.getSource('draw-circle-source')
        if (src) src.setData(geoJSON)

        if (onLocationSelect) {
          onLocationSelect({
            lat: _circleCenter[1],
            lon: _circleCenter[0],
            radius_m: Math.round(radiusM),
            vertices: geoJSON.geometry.coordinates[0],
          })
        }
        // App will set isSelectingLocation=false; useEffect resets cursor but
        // we deliberately do NOT clear the circle here — it stays visible.
        _circleCenter = null
      }
    })

    return () => {
      _dispatchAnim?.stop()
      _dispatchAnim = null
      DroneDotLayer.destroy()
      MapStateManager.destroy()
      _drawMapRef = null
      map.remove()
      mapRef.current = null
    }
  }, [])

  const statusColors = { NOMINAL: '#00FF88', ACTIVE: '#FFB800', EMERGENCY: '#FF3B3B' }
  const statusColor = statusColors[systemStatus] || statusColors.NOMINAL

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {/* Top-left: ARIA wordmark + status */}
      <div
        className="map-overlay interactive"
        style={{ top: 14, left: 14, display: 'flex', alignItems: 'center', gap: 10 }}
      >
        <span className="aria-wordmark">ARIA</span>
        <div className="status-badge" style={{ color: statusColor, borderColor: statusColor }}>
          {systemStatus || 'NOMINAL'}
        </div>
      </div>

      {/* Top-right: incident counters */}
      {Object.keys(incidents).length > 0 && (
        <div className="map-overlay" style={{ top: 14, right: 14 }}>
          <IncidentBadges incidents={incidents} />
        </div>
      )}

      {/* Bottom-left: coordinate readout */}
      <div className="map-overlay" style={{ bottom: 32, left: 14 }}>
        <div className="coord-readout">
          LAT {coords.lat.toFixed(4).padStart(9, ' ')}{'  '}
          LON {coords.lon.toFixed(4).padStart(10, ' ')}
        </div>
      </div>
    </div>
  )
}

export default Map

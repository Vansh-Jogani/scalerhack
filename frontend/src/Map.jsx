import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapStateManager from './MapStateManager.js'
import DroneManager from './DroneManager.js'
import { DISASTER_COLOR_MAP, MAX_ZONE_RADIUS_M } from './constants.js'
import responseCentres from './data/response_centres.json'
export { responseCentres }

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN

// Mapbox uses [lon, lat]; center is Hyderabad
const MAP_CENTER = [78.4867, 17.3850]
const MAP_ZOOM = 13

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

// Generate a GeoJSON polygon approximating a geographic circle
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

const TYPE_COLOURS = {
  FIRE_STATION: '#4FC3F7', NDRF: '#1565C0', SDRF: '#1E88E5',
  HOSPITAL: '#E53935', POLICE: '#5E35B1', CIVIL_DEFENCE: '#00897B',
  AIRPORT_EMERGENCY: '#F4511E', MUNICIPAL_EMERGENCY: '#039BE5',
}

let _drawColor = '#FF4500'
let _drawMapRef = null
let _centerMarker = null   // mapboxgl.Marker
let _circleCenter = null   // [lat, lon]

export function setDrawColor(color) {
  _drawColor = color
  if (_drawMapRef) {
    if (_drawMapRef.getLayer('draw-circle-fill')) _drawMapRef.setPaintProperty('draw-circle-fill', 'fill-color', color)
    if (_drawMapRef.getLayer('draw-circle-line')) _drawMapRef.setPaintProperty('draw-circle-line', 'line-color', color)
  }
  if (_centerMarker) {
    const dot = _centerMarker.getElement()?.firstChild
    if (dot) dot.style.borderColor = color
  }
}

export function clearDrawPolygon() {
  if (_centerMarker) { _centerMarker.remove(); _centerMarker = null }
  _circleCenter = null
  if (_drawMapRef?.getSource('draw-circle')) {
    _drawMapRef.getSource('draw-circle').setData({ type: 'FeatureCollection', features: [] })
  }
}


function Map({ isSelectingLocation, onLocationSelect }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const [coords, setCoords] = useState({ lat: 0, lon: 0 })
  const selectingRef = useRef(isSelectingLocation)

  useEffect(() => {
    selectingRef.current = isSelectingLocation
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = isSelectingLocation ? 'crosshair' : ''
    }
    if (isSelectingLocation) clearDrawPolygon()
  }, [isSelectingLocation])

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
    _drawMapRef = map

    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right')

    map.on('load', () => {
      // Response centres as small coloured dots
      responseCentres.forEach((rc) => {
        const color = TYPE_COLOURS[rc.type] || '#4FC3F7'
        const opacity = rc.verified ? 0.9 : 0.5
        const el = document.createElement('div')
        el.style.cssText = `width:10px;height:10px;border-radius:50%;background:${color};border:1.5px solid rgba(255,255,255,0.6);opacity:${opacity};cursor:pointer;box-sizing:border-box`
        const popup = new mapboxgl.Popup({ className: 'aria-popup', closeButton: false, offset: 8 })
          .setHTML(`
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#E8EDF5;min-width:160px">
              <div style="font-weight:600;margin-bottom:4px">${rc.name}</div>
              <div style="color:#7A8FA8">${rc.type.replace(/_/g, ' ')}</div>
              ${rc.address ? `<div style="color:#7A8FA8;margin-top:2px">${rc.address}</div>` : ''}
              ${!rc.verified ? '<div style="color:#FFB800;margin-top:4px">coords approximate</div>' : ''}
            </div>
          `)
        new mapboxgl.Marker(el, { anchor: 'center' }).setLngLat([rc.lon, rc.lat]).setPopup(popup).addTo(map)
      })

      // Zone-drawing GeoJSON source + layers (empty until user draws)
      map.addSource('draw-circle', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({ id: 'draw-circle-fill', type: 'fill', source: 'draw-circle', paint: { 'fill-color': _drawColor, 'fill-opacity': 0.15 } })
      map.addLayer({ id: 'draw-circle-line', type: 'line', source: 'draw-circle', paint: { 'line-color': _drawColor, 'line-width': 2, 'line-dasharray': [5, 3] } })

      MapStateManager.init(map, DroneManager, null)
      DroneManager.init(map)
    })

    map.on('mousemove', (e) => {
      const { lat, lng: lon } = e.lngLat
      setCoords({ lat, lon })
      if (selectingRef.current && _circleCenter) {
        const raw = haversineM(_circleCenter[0], _circleCenter[1], lat, lon)
        const radiusM = Math.min(raw, MAX_ZONE_RADIUS_M)
        if (radiusM >= 20 && map.getSource('draw-circle')) {
          map.getSource('draw-circle').setData(circleGeoJSON(_circleCenter[0], _circleCenter[1], radiusM))
          map.setPaintProperty('draw-circle-fill', 'fill-color', _drawColor)
          map.setPaintProperty('draw-circle-line', 'line-color', _drawColor)
        }
      }
    })

    map.on('click', (e) => {
      if (!selectingRef.current) return
      const { lat, lng: lon } = e.lngLat
      if (!_circleCenter) {
        _circleCenter = [lat, lon]
        const dotEl = document.createElement('div')
        dotEl.innerHTML = `<div style="width:10px;height:10px;border-radius:50%;background:white;border:2px solid ${_drawColor};box-sizing:border-box"></div>`
        _centerMarker = new mapboxgl.Marker(dotEl, { anchor: 'center' }).setLngLat([lon, lat]).addTo(map)
      } else {
        const radiusM = Math.min(haversineM(_circleCenter[0], _circleCenter[1], lat, lon), MAX_ZONE_RADIUS_M)
        if (radiusM < 20) return
        if (map.getSource('draw-circle')) map.getSource('draw-circle').setData(circleGeoJSON(_circleCenter[0], _circleCenter[1], radiusM))
        if (onLocationSelect) onLocationSelect({ lat: _circleCenter[0], lon: _circleCenter[1], radius_m: Math.round(radiusM) })
        _circleCenter = null
      }
    })

    return () => {
      DroneManager.destroy(); MapStateManager.destroy()
      _drawMapRef = null; _centerMarker = null; _circleCenter = null
      map.remove(); mapRef.current = null
    }
  }, [])

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div style={{
        position: 'absolute', bottom: 24, right: 16,
        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(180,200,220,0.5)',
        letterSpacing: '0.05em', pointerEvents: 'none',
      }}>
        {coords.lat.toFixed(5)}° N {'  '} {coords.lon.toFixed(5)}° E
      </div>
    </div>
  )
}

export default Map

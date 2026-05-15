import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import MapStateManager from './MapStateManager.js'
import DroneManager from './DroneManager.js'
import { DISASTER_COLORS, DISASTER_LABELS, DISASTER_COLOR_MAP, MAX_ZONE_RADIUS_M } from './constants.js'
import responseCentres from './data/response_centres.json'
import DispatchAnimation, { findNearestCentre } from './DispatchAnimation.js'

export { responseCentres }

const MAP_CENTER = [17.3850, 78.4867]
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

let _drawColor = '#FF4500'
let _drawMapRef = null
let _centerMarker = null
let _circleCenter = null
let _drawCircle = null
let _dispatchAnim = null

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

export function setDrawColor(color) {
  _drawColor = color
  if (_drawCircle) _drawCircle.setStyle({ color, fillColor: color })
  if (_centerMarker) {
    const el = _centerMarker.getElement()
    if (el) el.querySelector('div').style.borderColor = color
  }
}

export function clearDrawPolygon() {
  if (_centerMarker) { _drawMapRef?.removeLayer(_centerMarker); _centerMarker = null }
  if (_drawCircle) { _drawMapRef?.removeLayer(_drawCircle); _drawCircle = null }
  _circleCenter = null
}

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

  useEffect(() => {
    selectingRef.current = isSelectingLocation
    if (mapRef.current) {
      const container = mapRef.current.getContainer()
      container.style.cursor = isSelectingLocation ? 'crosshair' : ''
    }
    if (isSelectingLocation) {
      if (_centerMarker) { _drawMapRef?.removeLayer(_centerMarker); _centerMarker = null }
      if (_drawCircle) { _drawMapRef?.removeLayer(_drawCircle); _drawCircle = null }
      _circleCenter = null
    }
  }, [isSelectingLocation])

  useEffect(() => {
    if (mapRef.current) return
    const map = L.map(containerRef.current, {
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      zoomControl: false,
      attributionControl: false,
    })
    mapRef.current = map
    _drawMapRef = map

    L.control.zoom({ position: 'bottomright' }).addTo(map)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OSM &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map)

    const TYPE_COLOURS = {
      FIRE_STATION: '#4FC3F7', NDRF: '#1565C0', SDRF: '#1E88E5',
      HOSPITAL: '#E53935', POLICE: '#5E35B1', CIVIL_DEFENCE: '#00897B',
      AIRPORT_EMERGENCY: '#F4511E', MUNICIPAL_EMERGENCY: '#039BE5',
    }

    responseCentres.forEach((rc) => {
      const color = TYPE_COLOURS[rc.type] || '#4FC3F7'
      const opacity = rc.verified ? 0.9 : 0.5
      L.circleMarker([rc.lat, rc.lon], {
        radius: 5,
        fillColor: color,
        fillOpacity: opacity,
        color: 'white',
        weight: 0.5,
        opacity: opacity,
      }).addTo(map).bindPopup(`
        <div style="font-family:JetBrains Mono,monospace;font-size:11px;color:#E8EDF5;min-width:160px">
          <div style="font-weight:600;margin-bottom:4px">${rc.name}</div>
          <div style="color:#7A8FA8">${rc.type.replace(/_/g,' ')}</div>
          ${rc.address ? `<div style="color:#7A8FA8;margin-top:2px">${rc.address}</div>` : ''}
          ${!rc.verified ? '<div style="color:#FFB800;margin-top:4px">coords approximate</div>' : ''}
        </div>
      `, { className: 'aria-popup' })
    })

    MapStateManager.init(map, DroneManager, _onIncidentAdd)
    DroneManager.init(map)

    map.on('mousemove', (e) => {
      setCoords({ lat: e.latlng.lat, lon: e.latlng.lng })
      if (selectingRef.current && _circleCenter) {
        const raw = haversineM(_circleCenter[0], _circleCenter[1], e.latlng.lat, e.latlng.lng)
        const radiusM = Math.min(raw, MAX_ZONE_RADIUS_M)
        if (radiusM >= 20) {
          if (_drawCircle) {
            _drawCircle.setRadius(radiusM)
          } else {
            _drawCircle = L.circle([_circleCenter[0], _circleCenter[1]], {
              radius: radiusM, color: _drawColor, fillColor: _drawColor,
              fillOpacity: 0.15, weight: 2, dashArray: '5 3',
            }).addTo(map)
          }
        }
      }
    })

    map.on('click', (e) => {
      if (!selectingRef.current) return
      const { lat, lng } = e.latlng
      if (!_circleCenter) {
        _circleCenter = [lat, lng]
        const icon = L.divIcon({
          className: '',
          html: `<div style="width:10px;height:10px;border-radius:50%;background:white;border:2px solid ${_drawColor};box-sizing:border-box"></div>`,
          iconSize: [10, 10], iconAnchor: [5, 5],
        })
        _centerMarker = L.marker([lat, lng], { icon, interactive: false }).addTo(map)
      } else {
        const radiusM = Math.min(haversineM(_circleCenter[0], _circleCenter[1], lat, lng), MAX_ZONE_RADIUS_M)
        if (radiusM < 20) return
        if (_drawCircle) {
          _drawCircle.setRadius(radiusM)
        } else {
          _drawCircle = L.circle([_circleCenter[0], _circleCenter[1]], {
            radius: radiusM, color: _drawColor, fillColor: _drawColor,
            fillOpacity: 0.15, weight: 2, dashArray: '5 3',
          }).addTo(map)
        }
        if (onLocationSelect) {
          onLocationSelect({ lat: _circleCenter[0], lon: _circleCenter[1], radius_m: Math.round(radiusM) })
        }
        _circleCenter = null
      }
    })

    return () => {
      _dispatchAnim?.stop(); _dispatchAnim = null
      DroneManager.destroy(); MapStateManager.destroy()
      _drawMapRef = null; map.remove(); mapRef.current = null
    }
  }, [])

  const statusColors = { NOMINAL: '#00FF88', ACTIVE: '#FFB800', EMERGENCY: '#FF3B3B' }
  const statusColor = statusColors[systemStatus] || statusColors.NOMINAL

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div className="map-overlay interactive" style={{ top: 14, left: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="aria-wordmark">ARIA</span>
        <div className="status-badge" style={{ color: statusColor, borderColor: statusColor }}>
          {systemStatus || 'NOMINAL'}
        </div>
      </div>
      {Object.keys(incidents).length > 0 && (
        <div className="map-overlay" style={{ top: 14, right: 14 }}>
          <IncidentBadges incidents={incidents} />
        </div>
      )}
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

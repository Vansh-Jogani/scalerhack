import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import MapStateManager from './MapStateManager.js'
import DroneManager from './DroneManager.js'
import { DEFAULT_CENTER, DEFAULT_ZOOM, DISASTER_COLORS, DISASTER_LABELS } from './constants.js'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN

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
          <div
            key={type}
            className="incident-badge"
            style={{ color, borderColor: color }}
          >
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
  const [mapReady, setMapReady] = useState(false)
  const selectingRef = useRef(isSelectingLocation)

  // Keep selectingRef in sync so the click handler closure sees the latest value
  useEffect(() => {
    selectingRef.current = isSelectingLocation
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = isSelectingLocation ? 'crosshair' : ''
    }
  }, [isSelectingLocation])

  useEffect(() => {
    if (mapRef.current) return

    mapRef.current = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
    })

    mapRef.current.addControl(
      new mapboxgl.AttributionControl({ compact: true }),
      'bottom-right'
    )

    mapRef.current.on('load', () => {
      MapStateManager.init(mapRef.current, DroneManager, null)
      DroneManager.init(mapRef.current)
      setMapReady(true)
    })

    mapRef.current.on('mousemove', (e) => {
      setCoords({ lat: e.lngLat.lat, lon: e.lngLat.lng })
    })

    mapRef.current.on('click', (e) => {
      if (!selectingRef.current) return
      if (onLocationSelect) onLocationSelect({ lat: e.lngLat.lat, lon: e.lngLat.lng })
    })

    return () => {
      DroneManager.destroy()
      MapStateManager.destroy()
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [])

  const statusColors = {
    NOMINAL: '#00FF88',
    ACTIVE: '#FFB800',
    EMERGENCY: '#FF3B3B',
  }
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
        <div
          className="status-badge"
          style={{ color: statusColor, borderColor: statusColor }}
        >
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

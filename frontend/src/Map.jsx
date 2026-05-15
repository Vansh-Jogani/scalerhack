import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const RISK_COLORS = { low: '#44ff88', medium: '#ffcc00', high: '#ff8800', critical: '#ff2200' }

function Map({ drones, markers, zones, survivors, incident }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const droneMarkers = useRef({})
  const markerLayers = useRef({})
  const zoneLayers = useRef({})
  const survivorLayers = useRef([])
  const incidentCircle = useRef(null)
  const animTargets = useRef({})

  // Init map
  useEffect(() => {
    if (map.current) return
    map.current = L.map(mapContainer.current, {
      center: [34.0522, -118.2437],
      zoom: 14,
      zoomControl: true,
    })
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map.current)
    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  // Smooth drone animation
  useEffect(() => {
    let frameId
    const animate = () => {
      Object.entries(droneMarkers.current).forEach(([id, marker]) => {
        const target = animTargets.current[id]
        if (!target) return
        const pos = marker.getLatLng()
        const newLat = pos.lat + (target.lat - pos.lat) * 0.15
        const newLng = pos.lng + (target.lon - pos.lng) * 0.15
        marker.setLatLng([newLat, newLng])
        const el = marker.getElement()
        if (el) {
          const arrow = el.querySelector('.drone-icon')
          if (arrow) arrow.style.transform = `rotate(${target.heading || 0}deg)`
        }
      })
      frameId = requestAnimationFrame(animate)
    }
    frameId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameId)
  }, [])

  // Drone icons
  useEffect(() => {
    if (!map.current) return
    Object.entries(drones).forEach(([id, data]) => {
      animTargets.current[id] = { lat: data.lat, lon: data.lon, heading: data.heading }
      if (!droneMarkers.current[id]) {
        const isSwarm = id.startsWith('swarm')
        const color = isSwarm ? '#ffaa00' : '#00aaff'
        const size = isSwarm ? 14 : 18
        const icon = L.divIcon({
          className: '',
          html: `<div style="width:${size+6}px;height:${size+6}px;display:flex;align-items:center;justify-content:center;">
                   <div class="drone-icon" style="width:${size}px;height:${size}px;background:${color};
                     clip-path:polygon(50% 0%,0% 100%,50% 80%,100% 100%);
                     filter:drop-shadow(0 0 4px ${color});"></div>
                 </div>`,
          iconSize: [size + 6, size + 6],
          iconAnchor: [(size + 6) / 2, (size + 6) / 2],
        })
        const m = L.marker([data.lat, data.lon], { icon }).addTo(map.current)
        m.bindTooltip(id, { permanent: false, direction: 'right', className: 'drone-tooltip' })
        droneMarkers.current[id] = m
      }
    })
  }, [drones])

  // Incident markers (from scenario)
  useEffect(() => {
    if (!map.current) return
    markers.forEach((m) => {
      if (markerLayers.current[m.id]) return
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:14px;height:14px;background:#ff4400;border-radius:50%;
                 border:2px solid #ff8866;box-shadow:0 0 10px #ff4400,0 0 20px rgba(255,68,0,0.4);
                 animation:pulse 2s infinite;"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      })
      const marker = L.marker([m.lat, m.lon], { icon }).addTo(map.current)
      marker.bindPopup(`<b>${m.type}</b><br>Severity: ${m.severity}<br>Radius: ${m.radius_m}m`)
      markerLayers.current[m.id] = marker
    })
  }, [markers])

  // Confirmed incident circle (from Agent 1 classification)
  useEffect(() => {
    if (!map.current || !incident) return
    if (incidentCircle.current) {
      incidentCircle.current.remove()
    }
    incidentCircle.current = L.circle(
      [incident.center.lat, incident.center.lon],
      {
        radius: incident.radius_m,
        color: '#ff6600',
        fillColor: '#ff4400',
        fillOpacity: 0.08,
        weight: 2,
        dashArray: '6 4',
      }
    ).addTo(map.current)
    incidentCircle.current.bindPopup(
      `<b>${incident.classification.toUpperCase()}</b><br>Confidence: ${(incident.confidence * 100).toFixed(0)}%`
    )
  }, [incident])

  // Zone risk circles (from Agent 2)
  useEffect(() => {
    if (!map.current) return
    zones.forEach((z) => {
      if (zoneLayers.current[z.zone_id]) return
      const color = RISK_COLORS[z.risk_level] || '#888'
      zoneLayers.current[z.zone_id] = L.circle([z.lat, z.lon], {
        radius: 40,
        color,
        fillColor: color,
        fillOpacity: 0.25,
        weight: 1,
      }).addTo(map.current)
    })
  }, [zones])

  // Survivor markers
  useEffect(() => {
    if (!map.current) return
    const existing = survivorLayers.current.length
    survivors.slice(existing).forEach((s) => {
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:12px;height:12px;background:#00ffaa;border-radius:50%;
                 border:2px solid #ffffff;box-shadow:0 0 8px #00ffaa;"></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      })
      const m = L.marker([s.lat, s.lon], { icon }).addTo(map.current)
      m.bindPopup(`Survivor — confidence ${(s.confidence * 100).toFixed(0)}%`)
      survivorLayers.current.push(m)
    })
  }, [survivors])

  return (
    <>
      <style>{`
        .drone-tooltip { background: rgba(0,0,0,0.8); color: #00aaff; border: 1px solid #00aaff; font-family: monospace; font-size: 11px; }
        @keyframes pulse { 0%,100% { box-shadow: 0 0 10px #ff4400; } 50% { box-shadow: 0 0 20px #ff8800, 0 0 30px rgba(255,68,0,0.6); } }
      `}</style>
      <div ref={mapContainer} style={{ width: '100%', height: '100%', background: '#0d0d0d' }} />
    </>
  )
}

export default Map

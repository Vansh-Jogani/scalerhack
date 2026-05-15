import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN
console.log('[ARIA] token:', import.meta.env.VITE_MAPBOX_TOKEN ? import.meta.env.VITE_MAPBOX_TOKEN.slice(0, 15) + '…' : 'MISSING')

function Map({ drones, markers }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const droneMarkers = useRef({})
  const markerLayers = useRef({})
  const animationTargets = useRef({})
  const [mapReady, setMapReady] = useState(false)

  useEffect(() => {
    if (map.current) return
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [-118.2437, 34.0522],
      zoom: 13,
    })
    map.current.on('load', () => {
      console.log('[ARIA] Map loaded ✓')
      setMapReady(true)
    })
    map.current.on('error', (e) => console.error('[ARIA] Map error:', e))
    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  // Add/update drone icons — only once map style is ready
  useEffect(() => {
    if (!mapReady) return
    console.log('[ARIA] drones effect, count:', Object.keys(drones).length)
    Object.entries(drones).forEach(([id, data]) => {
      animationTargets.current[id] = { lat: data.lat, lon: data.lon, heading: data.heading }
      if (droneMarkers.current[id]) return

      const wrapper = document.createElement('div')
      wrapper.style.cssText = 'width:24px;height:24px;display:flex;align-items:center;justify-content:center;'
      const arrow = document.createElement('div')
      arrow.className = 'drone-arrow'
      arrow.style.cssText = 'width:16px;height:16px;background:#00ffaa;clip-path:polygon(50% 0%,0% 100%,100% 100%);'
      wrapper.appendChild(arrow)

      droneMarkers.current[id] = new mapboxgl.Marker({ element: wrapper })
        .setLngLat([data.lon, data.lat])
        .addTo(map.current)
    })
  }, [drones, mapReady])

  // RAF lerp loop
  useEffect(() => {
    let frameId
    const animate = () => {
      Object.entries(droneMarkers.current).forEach(([id, marker]) => {
        const target = animationTargets.current[id]
        if (!target) return
        const cur = marker.getLngLat()
        marker.setLngLat([
          cur.lng + (target.lon - cur.lng) * 0.1,
          cur.lat + (target.lat - cur.lat) * 0.1,
        ])
        const arrow = marker.getElement().querySelector('.drone-arrow')
        if (arrow) arrow.style.transform = `rotate(${target.heading || 0}deg)`
      })
      frameId = requestAnimationFrame(animate)
    }
    frameId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameId)
  }, [])

  // Add disaster markers — only once map style is ready
  useEffect(() => {
    if (!mapReady) return
    console.log('[ARIA] markers effect, count:', markers.length)
    markers.forEach((m) => {
      if (markerLayers.current[m.id]) return
      const el = document.createElement('div')
      el.style.cssText = 'width:16px;height:16px;background:#ff4444;border-radius:50%;border:2px solid #ff8888;box-shadow:0 0 8px #ff4444;'
      markerLayers.current[m.id] = new mapboxgl.Marker({ element: el })
        .setLngLat([m.lon, m.lat])
        .addTo(map.current)
    })
  }, [markers, mapReady])

  return <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
}

export default Map

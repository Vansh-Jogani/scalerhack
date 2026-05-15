import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN

function Map({ drones, markers }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const droneMarkers = useRef({})
  const markerLayers = useRef({})
  const animationTargets = useRef({})

  useEffect(() => {
    if (map.current) return
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [-118.2437, 34.0522],
      zoom: 13,
    })
    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  // Animate drones with lerp
  useEffect(() => {
    if (!map.current) return
    Object.entries(drones).forEach(([id, data]) => {
      animationTargets.current[id] = { lat: data.lat, lon: data.lon, heading: data.heading }

      if (!droneMarkers.current[id]) {
        const wrapper = document.createElement('div')
        wrapper.className = 'drone-marker'
        wrapper.style.cssText = 'width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;'
        const arrow = document.createElement('div')
        arrow.className = 'drone-arrow'
        arrow.style.cssText = `
          width: 16px; height: 16px;
          background: #00ffaa;
          clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
        `
        wrapper.appendChild(arrow)
        droneMarkers.current[id] = new mapboxgl.Marker({ element: wrapper })
          .setLngLat([data.lon, data.lat])
          .addTo(map.current)
      }
    })
  }, [drones])

  // RAF lerp loop
  useEffect(() => {
    let frameId
    const animate = () => {
      Object.entries(droneMarkers.current).forEach(([id, marker]) => {
        const target = animationTargets.current[id]
        if (!target) return
        const current = marker.getLngLat()
        const newLng = current.lng + (target.lon - current.lng) * 0.1
        const newLat = current.lat + (target.lat - current.lat) * 0.1
        marker.setLngLat([newLng, newLat])
        const arrow = marker.getElement().querySelector('.drone-arrow')
        if (arrow) arrow.style.transform = `rotate(${target.heading || 0}deg)`
      })
      frameId = requestAnimationFrame(animate)
    }
    frameId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameId)
  }, [])

  // Render disaster markers
  useEffect(() => {
    if (!map.current) return
    markers.forEach((m) => {
      if (markerLayers.current[m.id]) return
      const el = document.createElement('div')
      el.style.cssText = `
        width: 16px; height: 16px;
        background: #ff4444;
        border-radius: 50%;
        border: 2px solid #ff8888;
        box-shadow: 0 0 8px #ff4444;
      `
      markerLayers.current[m.id] = new mapboxgl.Marker({ element: el })
        .setLngLat([m.lon, m.lat])
        .addTo(map.current)
    })
  }, [markers])

  return <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
}

export default Map

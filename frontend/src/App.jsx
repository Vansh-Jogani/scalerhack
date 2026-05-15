import { useState, useEffect, useRef } from 'react'
import Map from './Map'

function App() {
  const [droneData, setDroneData] = useState({})
  const [markers, setMarkers] = useState([])
  const ws = useRef(null)

  useEffect(() => {
    ws.current = new WebSocket(`ws://${window.location.host}/ws`)
    ws.current.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'telemetry') {
        setDroneData((prev) => ({ ...prev, [msg.data.drone_id]: msg.data }))
      } else if (msg.type === 'markers') {
        setMarkers(msg.data)
      }
    }
    return () => ws.current?.close()
  }, [])

  return <Map drones={droneData} markers={markers} />
}

export default App

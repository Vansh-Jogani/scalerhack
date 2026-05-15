import { useState, useEffect, useRef } from 'react'
import Map from './Map'
import AgentStream from './AgentStream'
import AdvisoryPanel from './AdvisoryPanel'
import DroneStatus from './DroneStatus'

function App() {
  const [droneData, setDroneData] = useState({})
  const [markers, setMarkers] = useState([])
  const [agentStream, setAgentStream] = useState([])
  const [advisory, setAdvisory] = useState(null)
  const ws = useRef(null)

  useEffect(() => {
    const socket = new WebSocket(`ws://${window.location.host}/ws`)
    ws.current = socket
    socket.onopen = () => console.log('[ARIA] WS connected to', socket.url)
    socket.onerror = (e) => console.error('[ARIA] WS error', e)
    socket.onclose = (e) => console.warn('[ARIA] WS closed', e.code, e.reason)
    let msgCount = 0
    socket.onmessage = (event) => {
      msgCount++
      if (msgCount <= 3 || msgCount % 50 === 0) console.log('[ARIA] msg #' + msgCount, event.data.slice(0, 80))
      const msg = JSON.parse(event.data)
      if (msg.type === 'telemetry') {
        setDroneData((prev) => ({ ...prev, [msg.data.drone_id]: msg.data }))
      } else if (msg.type === 'markers') {
        setMarkers(msg.data)
      } else if (msg.type === 'agent_stream') {
        setAgentStream((prev) => [...prev.slice(-49), { ...msg.data, ts: Date.now() }])
      } else if (msg.type === 'advisory') {
        setAdvisory(msg.data)
      }
    }
    return () => socket.close()
  }, [])

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', background: '#0a0a0a', overflow: 'hidden' }}>
      <Map drones={droneData} markers={markers} />
      <DroneStatus drones={droneData} />
      <AgentStream events={agentStream} />
      <AdvisoryPanel advisory={advisory} />
    </div>
  )
}

export default App

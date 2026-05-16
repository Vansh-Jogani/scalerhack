export const DISASTER_COLORS = {
  FIRE:                '#FF3B3B',
  STRUCTURAL_COLLAPSE: '#FF8C42',
  FLOOD:               '#2196F3',
  INDUSTRIAL_HAZARD:   '#9E9E9E',
  MARITIME_SAR:        '#00CED1',
}

// Normalised key lookup (backend sends lowercase)
export const DISASTER_COLOR_MAP = {
  fire:                '#FF3B3B',
  structural_collapse: '#FF8C42',
  flood:               '#2196F3',
  industrial_hazard:   '#9E9E9E',
  maritime_sar:        '#00CED1',
}

// SVG icon paths (24×24 viewBox) for disaster pin centres
export const DISASTER_ICON_PATHS = {
  fire: `<path d="M12 2C12 2 8 7 8 11c0 2.2 1.8 4 4 4s4-1.8 4-4c0-1.5-1-3-1-3s-.5 2-2 2c-1.1 0-2-.9-2-2 0-1.5 1-3 1-4z M10 17h4v2h-4z" fill="white"/>`,
  structural_collapse: `<path d="M4 20L12 4l8 16H4zm2.5-2h11l-5.5-11-5.5 11z M11 14h2v2h-2z M11 10h2v3h-2z" fill="white"/>`,
  flood: `<path d="M3 16.5c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1v2c-1.5 0-2.5-1-4-1s-2.5 1-4 1-2.5-1-4-1-2.5 1-4 1v-2z M3 12.5c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1v2c-1.5 0-2.5-1-4-1s-2.5 1-4 1-2.5-1-4-1-2.5 1-4 1v-2z M12 3L8 9h8l-4-6z" fill="white"/>`,
  industrial_hazard: `<path d="M12 2l2 4h4l-3.5 2.5 1.5 4L12 10l-4 2.5 1.5-4L6 6h4l2-4z M11 14h2v6h-2z M9 15h6v1H9z" fill="white"/>`,
  maritime_sar: `<path d="M3 18h18v2H3v-2z M5 14l7-10 7 10H5z M10 10h4v3h-4z" fill="white"/>`,
}

export const SEVERITY_RADII = {
  CRITICAL: { inner: 300, mid: 800, outer: 2000 },
  HIGH:     { inner: 200, mid: 600, outer: 1500 },
  MEDIUM:   { inner: 150, mid: 400, outer: 1000 },
  LOW:      { inner: 100, mid: 250, outer: 600 },
}

export const DRONE_STATES = {
  FLYING:       '#00FF88',
  LOITERING:    '#FFB800',
  IDLE:         '#7A8FA8',
  THERMAL_SCAN: '#00BFFF',
  RTL:          '#FF3B3B',
}

export const AGENT_COLORS = {
  ORCHESTRATOR: null,
  AGENT_1: '#7B68EE',
  AGENT_2: null, // set to active incident disaster color
  AGENT_3: '#00FF88',
  AGENT_4: '#FF6B35',
}

export const DEFAULT_CENTER = [78.39, 17.44]
export const DEFAULT_ZOOM = 13

export const SYSTEM_STATUS = {
  NOMINAL:   { label: 'NOMINAL',   color: '#00FF88' },
  ACTIVE:    { label: 'ACTIVE',    color: '#FFB800' },
  EMERGENCY: { label: 'EMERGENCY', color: '#FF3B3B' },
}

export const DISASTER_LABELS = {
  FIRE: 'FIRE',
  STRUCTURAL_COLLAPSE: 'STRUCTURAL',
  FLOOD: 'FLOOD',
  INDUSTRIAL_HAZARD: 'INDUSTRIAL',
  MARITIME_SAR: 'MARITIME SAR',
}

export const SEVERITY_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
export const DISASTER_TYPES = ['FIRE', 'STRUCTURAL_COLLAPSE', 'FLOOD', 'INDUSTRIAL_HAZARD', 'MARITIME_SAR']

export const MAX_ZONE_RADIUS_M = 1000

// Global disaster response centres — drone origin points
// Agent picks nearest centre to the triggered incident
export const RESPONSE_CENTRES = [
  { id: 'drc-hyderabad',      name: 'Hyderabad DRC',      country: 'India',        lat: 17.3850,   lon:  78.4867  },
  { id: 'drc-mumbai',         name: 'Mumbai DRC',          country: 'India',        lat: 19.0760,   lon:  72.8777  },
  { id: 'drc-delhi',          name: 'Delhi DRC',           country: 'India',        lat: 28.6139,   lon:  77.2090  },
  { id: 'drc-chennai',        name: 'Chennai DRC',         country: 'India',        lat: 13.0827,   lon:  80.2707  },
  { id: 'drc-london',         name: 'London DRC',          country: 'UK',           lat: 51.5074,   lon:  -0.1278  },
  { id: 'drc-paris',          name: 'Paris DRC',           country: 'France',       lat: 48.8566,   lon:   2.3522  },
  { id: 'drc-berlin',         name: 'Berlin DRC',          country: 'Germany',      lat: 52.5200,   lon:  13.4050  },
  { id: 'drc-istanbul',       name: 'Istanbul DRC',        country: 'Turkey',       lat: 41.0082,   lon:  28.9784  },
  { id: 'drc-moscow',         name: 'Moscow DRC',          country: 'Russia',       lat: 55.7558,   lon:  37.6173  },
  { id: 'drc-dubai',          name: 'Dubai DRC',           country: 'UAE',          lat: 25.2048,   lon:  55.2708  },
  { id: 'drc-karachi',        name: 'Karachi DRC',         country: 'Pakistan',     lat: 24.8607,   lon:  67.0011  },
  { id: 'drc-cairo',          name: 'Cairo DRC',           country: 'Egypt',        lat: 30.0444,   lon:  31.2357  },
  { id: 'drc-nairobi',        name: 'Nairobi DRC',         country: 'Kenya',        lat: -1.2921,   lon:  36.8219  },
  { id: 'drc-lagos',          name: 'Lagos DRC',           country: 'Nigeria',      lat:  6.5244,   lon:   3.3792  },
  { id: 'drc-johannesburg',   name: 'Johannesburg DRC',    country: 'South Africa', lat: -26.2041,  lon:  28.0473  },
  { id: 'drc-singapore',      name: 'Singapore DRC',       country: 'Singapore',    lat:  1.3521,   lon: 103.8198  },
  { id: 'drc-bangkok',        name: 'Bangkok DRC',         country: 'Thailand',     lat: 13.7563,   lon: 100.5018  },
  { id: 'drc-jakarta',        name: 'Jakarta DRC',         country: 'Indonesia',    lat: -6.2088,   lon: 106.8456  },
  { id: 'drc-shanghai',       name: 'Shanghai DRC',        country: 'China',        lat: 31.2304,   lon: 121.4737  },
  { id: 'drc-tokyo',          name: 'Tokyo DRC',           country: 'Japan',        lat: 35.6762,   lon: 139.6503  },
  { id: 'drc-sydney',         name: 'Sydney DRC',          country: 'Australia',    lat: -33.8688,  lon: 151.2093  },
  { id: 'drc-new-york',       name: 'New York DRC',        country: 'USA',          lat: 40.7128,   lon: -74.0060  },
  { id: 'drc-los-angeles',    name: 'Los Angeles DRC',     country: 'USA',          lat: 34.0522,   lon: -118.2437 },
  { id: 'drc-chicago',        name: 'Chicago DRC',         country: 'USA',          lat: 41.8781,   lon: -87.6298  },
  { id: 'drc-miami',          name: 'Miami DRC',           country: 'USA',          lat: 25.7617,   lon: -80.1918  },
  { id: 'drc-toronto',        name: 'Toronto DRC',         country: 'Canada',       lat: 43.6532,   lon: -79.3832  },
  { id: 'drc-mexico-city',    name: 'Mexico City DRC',     country: 'Mexico',       lat: 19.4326,   lon: -99.1332  },
  { id: 'drc-sao-paulo',      name: 'São Paulo DRC',       country: 'Brazil',       lat: -23.5505,  lon: -46.6333  },
  { id: 'drc-buenos-aires',   name: 'Buenos Aires DRC',    country: 'Argentina',    lat: -34.6037,  lon: -58.3816  },
  { id: 'drc-lima',           name: 'Lima DRC',            country: 'Peru',         lat: -12.0464,  lon: -77.0428  },
]

export const DISASTER_COLORS = {
  FIRE: '#FF4500',
  STRUCTURAL_COLLAPSE: '#FF8C00',
  FLOOD: '#00BFFF',
  INDUSTRIAL_HAZARD: '#ADFF2F',
  MARITIME_SAR: '#00CED1',
}

// Normalised key lookup (backend sends lowercase)
export const DISASTER_COLOR_MAP = {
  fire: '#FF4500',
  structural_collapse: '#FF8C00',
  flood: '#00BFFF',
  industrial_hazard: '#ADFF2F',
  maritime_sar: '#00CED1',
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

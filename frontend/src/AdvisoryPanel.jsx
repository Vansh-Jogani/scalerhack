import { motion, AnimatePresence } from 'framer-motion'

const SECTION_ORDER = [
  { key: 'SITUATION SUMMARY',     type: 'body',     listClass: null },
  { key: 'IMMEDIATE ACTIONS',     type: 'mono-list', listClass: null },
  { key: 'EXCLUSION ZONES',       type: 'list',     listClass: 'exclusion' },
  { key: 'RESOURCE REQUIREMENTS', type: 'body',     listClass: null },
  { key: 'RISK FLAGS',            type: 'list',     listClass: 'risk' },
  { key: 'MONITORING',            type: 'secondary', listClass: null },
]

// Parse Agent 3 raw text output into section map
function parseAdvisory(rawText) {
  if (!rawText) return null
  const sections = {}
  let currentKey = null
  const lines = rawText.split('\n')

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    // Detect section headers like "SITUATION SUMMARY:" or "IMMEDIATE ACTIONS (next 15 min):"
    const headerMatch = trimmed.match(/^([A-Z][A-Z\s()]+):\s*(.*)/)
    if (headerMatch) {
      const candidate = headerMatch[1].trim()
      const matched = SECTION_ORDER.find((s) =>
        s.key === candidate || candidate.startsWith(s.key)
      )
      if (matched) {
        currentKey = matched.key
        sections[currentKey] = sections[currentKey] || []
        if (headerMatch[2]) sections[currentKey].push(headerMatch[2].trim())
        continue
      }
    }

    if (currentKey) {
      sections[currentKey].push(trimmed)
    }
  }

  return sections
}

function SectionContent({ type, listClass, lines }) {
  if (!lines || lines.length === 0) return null

  if (type === 'body') {
    return (
      <p className="advisory-section-body">
        {lines.join(' ')}
      </p>
    )
  }

  if (type === 'secondary') {
    return (
      <p className="advisory-section-body" style={{ color: 'var(--text-secondary)' }}>
        {lines.join(' ')}
      </p>
    )
  }

  if (type === 'mono-list') {
    return (
      <ol className="advisory-list" style={{ paddingLeft: 0, listStylePosition: 'inside' }}>
        {lines.map((line, i) => (
          <li key={i} className="advisory-mono" style={{ borderLeft: 'none', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            {i + 1}. {line.replace(/^\d+[\.\)]\s*/, '')}
          </li>
        ))}
      </ol>
    )
  }

  return (
    <ul className={`advisory-list${listClass ? ' ' + listClass : ''}`}>
      {lines.map((line, i) => (
        <li key={i}>{line.replace(/^[-•]\s*/, '')}</li>
      ))}
    </ul>
  )
}

function AdvisoryPanel({ advisory }) {
  const parsed = parseAdvisory(advisory?.text)
  const updatedAt = advisory?.timestamp || null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--surface)' }}>
      <div className="panel-header">
        <span>ADVISORY&nbsp;&nbsp;[AGENT 3]</span>
        {updatedAt && (
          <span style={{
            fontSize: 10,
            fontWeight: 400,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
            letterSpacing: '0.05em',
          }}>
            UPDATED {updatedAt}
          </span>
        )}
      </div>

      <div className="panel-body" style={{ overflowY: 'auto' }}>
        {!parsed ? (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}>
            NO ACTIVE ADVISORY
          </div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={advisory?.timestamp}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {SECTION_ORDER.map((section, idx) => {
                const lines = parsed[section.key]
                if (!lines || lines.length === 0) return null
                return (
                  <motion.div
                    key={section.key}
                    className="advisory-section"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: idx * 0.08 }}
                  >
                    <div className="advisory-section-label">{section.key}</div>
                    <SectionContent
                      type={section.type}
                      listClass={section.listClass}
                      lines={lines}
                    />
                  </motion.div>
                )
              })}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}

export default AdvisoryPanel

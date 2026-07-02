export default function Logo({ size = 44, wordmark = true, variant = 'dark' }) {
  const textColor = variant === 'light' ? '#ffffff' : '#CC1212'
  const subColor  = variant === 'light' ? 'rgba(255,255,255,.8)' : '#6b6b7b'
  const nameSize  = Math.round(size * 0.5)
  const subSize   = Math.max(9, Math.round(size * 0.23))
  const r         = Math.round(size * 0.18)

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
      <svg width={size} height={size} viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-label="Caja Trujillo" role="img">
        <rect x="1" y="1" width="46" height="46" rx={r} fill="#CC1212" />
        <circle cx="38" cy="10" r="6" fill="#F5A623" />
        <path d="M 12 38 L 20 12 L 28 12 L 36 38 L 29 38 L 27 30 L 21 30 L 19 38 Z M 22 24 L 26 24 L 24 16 Z" fill="#FFFFFF" />
        <path d="M 10 42 Q 24 36 38 42" stroke="#F7C948" strokeWidth="3.5" fill="none" strokeLinecap="round" />
      </svg>
      {wordmark && (
        <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.04 }}>
          <span style={{ fontWeight: 800, fontSize: nameSize, color: textColor, letterSpacing: '-0.5px' }}>
            Caja Trujillo
          </span>
          <span style={{ fontSize: subSize, fontWeight: 700, color: subColor, letterSpacing: '1.2px' }}>
            CORE FINANCIERO
          </span>
        </span>
      )}
    </span>
  )
}
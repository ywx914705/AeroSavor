/**
 * AeroSavor Logo — Modern Minimal
 *
 * Concept: A speech bubble (AI/chat) seamlessly merged with a fork (food/dining).
 * Clean geometry, rounded forms, works at any size.
 * Gradient: warm amber to orange for an appetizing, modern feel.
 */

interface LogoProps {
  size?: number
  className?: string
  withWordmark?: boolean
  iconOnly?: boolean
}

export function AeroSavorLogo({ size = 40, className = "", withWordmark = false, iconOnly = false }: LogoProps) {
  const viewBox = iconOnly ? "0 0 48 48" : withWordmark ? "0 0 220 48" : "0 0 48 48"

  return (
    <svg
      width={iconOnly ? size : withWordmark ? size * 4.6 : size}
      height={size}
      viewBox={viewBox}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="AeroSavor"
    >
      <defs>
        <linearGradient id="as-grad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#EA580C" />
        </linearGradient>
      </defs>

      {/* Icon: Speech bubble + fork */}
      <g transform="translate(4, 4)">
        {/* Speech bubble body */}
        <rect x="2" y="2" width="36" height="28" rx="10" fill="url(#as-grad)" />
        {/* Speech bubble tail */}
        <path d="M10 30 L6 38 L18 30" fill="url(#as-grad)" />

        {/* Fork — white, centered in bubble */}
        <g transform="translate(14, 7)" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none">
          {/* Left tine */}
          <line x1="4" y1="1" x2="4" y2="9" />
          {/* Center tine */}
          <line x1="10" y1="1" x2="10" y2="9" />
          {/* Right tine */}
          <line x1="16" y1="1" x2="16" y2="9" />
          {/* Connecting arc */}
          <path d="M4 9 C4 15, 16 15, 16 9" />
          {/* Handle */}
          <line x1="10" y1="13" x2="10" y2="22" />
        </g>
      </g>

      {/* Wordmark */}
      {withWordmark && (
        <g transform="translate(58, 8)">
          <text
            x="0" y="26"
            fontFamily="'Epilogue', sans-serif"
            fontWeight="800"
            fontSize="22"
            letterSpacing="-0.03em"
          >
            <tspan fill="#F59E0B">Aero</tspan>
            <tspan fill="#1a1a1a">Savor</tspan>
          </text>
          <text
            x="0" y="40"
            fontFamily="'Epilogue', sans-serif"
            fontWeight="500"
            fontSize="9"
            fill="#94a3b8"
            letterSpacing="0.06em"
          >
            Multi-Agent 推荐
          </text>
        </g>
      )}
    </svg>
  )
}

/**
 * Compact icon-only — for avatars, favicons, small spaces
 */
export function AeroSavorIcon({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="AeroSavor"
    >
      <defs>
        <linearGradient id="as-grad-sm" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#EA580C" />
        </linearGradient>
      </defs>
      <rect x="4" y="2" width="40" height="32" rx="11" fill="url(#as-grad-sm)" />
      <path d="M12 34 L8 42 L20 34" fill="url(#as-grad-sm)" />
      <g transform="translate(16, 8)" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none">
        <line x1="4" y1="1" x2="4" y2="10" />
        <line x1="10" y1="1" x2="10" y2="10" />
        <line x1="16" y1="1" x2="16" y2="10" />
        <path d="M4 10 C4 17, 16 17, 16 10" />
        <line x1="10" y1="14" x2="10" y2="23" />
      </g>
    </svg>
  )
}

/**
 * Mini version for inline/favicon (16x16 friendly)
 */
export function AeroSavorMini({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="AeroSavor"
    >
      <defs>
        <linearGradient id="as-grad-xs" x1="0" y1="0" x2="20" y2="20" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#EA580C" />
        </linearGradient>
      </defs>
      <rect x="1.5" y="1" width="17" height="13.5" rx="4.5" fill="url(#as-grad-xs)" />
      <path d="M5 14.5 L3.5 18 L8.5 14.5" fill="url(#as-grad-xs)" />
      <g transform="translate(6.5, 3.5)" stroke="white" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none">
        <line x1="1.5" y1="0.5" x2="1.5" y2="4" />
        <line x1="4" y1="0.5" x2="4" y2="4" />
        <line x1="6.5" y1="0.5" x2="6.5" y2="4" />
        <path d="M1.5 4 C1.5 7, 6.5 7, 6.5 4" />
        <line x1="4" y1="5.5" x2="4" y2="9.5" />
      </g>
    </svg>
  )
}

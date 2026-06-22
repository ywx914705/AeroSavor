import { useMemo } from "react"

interface Particle {
  id: number
  size: number
  x: number
  y: number
  duration: number
  delay: number
  animClass: string
  color: string
}

const PARTICLE_COUNT = 24
const ANIMATIONS = ["particle-float-1", "particle-float-2", "particle-float-3", "particle-float-4"]
const COLORS = [
  "rgba(245, 158, 11, 0.4)",
  "rgba(251, 191, 36, 0.35)",
  "rgba(234, 88, 12, 0.3)",
  "rgba(245, 158, 11, 0.25)",
]

export function AmbientParticles({ className = "" }: { className?: string }) {
  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      id: i,
      size: 2 + (i % 5) * 1.5,
      x: (i * 37 + 13) % 100,
      y: (i * 53 + 7) % 100,
      duration: 12 + (i % 7) * 4,
      delay: (i * 1.3) % 8,
      animClass: ANIMATIONS[i % ANIMATIONS.length],
      color: COLORS[i % COLORS.length],
    }))
  }, [])

  return (
    <div className={`absolute inset-0 overflow-hidden pointer-events-none ${className}`}>
      {particles.map((p) => (
        <div
          key={p.id}
          className="ambient-particle"
          style={{
            width: p.size,
            height: p.size,
            left: `${p.x}%`,
            top: `${p.y}%`,
            background: p.color,
            animation: `${p.animClass} ${p.duration}s ease-in-out infinite`,
            animationDelay: `${p.delay}s`,
            filter: `blur(${p.size > 5 ? 1 : 0}px)`,
          }}
        />
      ))}
    </div>
  )
}

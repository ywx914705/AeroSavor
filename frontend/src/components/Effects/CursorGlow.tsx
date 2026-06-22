import { useEffect, useRef, useCallback } from "react"

/**
 * 全局鼠标光效 — 一个跟随鼠标的柔和 radial gradient
 * 类似 Linear / Vercel 的 cursor glow
 */
export function CursorGlow() {
  const glowRef = useRef<HTMLDivElement>(null)
  const raf = useRef(0)

  const handleMove = useCallback((e: MouseEvent) => {
    if (raf.current) cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(() => {
      const el = glowRef.current
      if (el) {
        el.style.left = `${e.clientX}px`
        el.style.top = `${e.clientY}px`
        el.style.opacity = "1"
      }
    })
  }, [])

  const handleLeave = useCallback(() => {
    const el = glowRef.current
    if (el) el.style.opacity = "0"
  }, [])

  useEffect(() => {
    window.addEventListener("mousemove", handleMove, { passive: true })
    document.addEventListener("mouseleave", handleLeave)
    return () => {
      window.removeEventListener("mousemove", handleMove)
      document.removeEventListener("mouseleave", handleLeave)
      if (raf.current) cancelAnimationFrame(raf.current)
    }
  }, [handleMove, handleLeave])

  return (
    <div
      ref={glowRef}
      className="fixed pointer-events-none z-[9999] -translate-x-1/2 -translate-y-1/2"
      style={{
        width: 600,
        height: 600,
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(245,158,11,0.045) 0%, rgba(245,158,11,0.015) 35%, transparent 65%)",
        opacity: 0,
        transition: "opacity 0.8s ease",
        willChange: "left, top",
      }}
    />
  )
}

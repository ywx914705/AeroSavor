import { useEffect, useRef } from "react"

/** Subtle grain texture overlay */
function GrainOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let running = true
    let frame = 0

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener("resize", resize)

    const draw = () => {
      if (!running) return
      if (frame++ % 4 === 0) {
        const w = canvas.width
        const h = canvas.height
        const imageData = ctx.createImageData(w, h)
        const data = imageData.data
        for (let i = 0; i < data.length; i += 4) {
          const v = Math.random() * 255
          data[i] = v
          data[i + 1] = v
          data[i + 2] = v
          data[i + 3] = 12
        }
        ctx.putImageData(imageData, 0, 0)
      }
      requestAnimationFrame(draw)
    }
    draw()

    return () => {
      running = false
      window.removeEventListener("resize", resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="grain-texture" />
}

export function BackgroundEffects() {
  return (
    <>
      <GrainOverlay />
    </>
  )
}

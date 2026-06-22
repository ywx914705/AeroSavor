import { useEffect, useState } from "react"

/** Returns formatted elapsed time string for a running step.
 *  Updates every second while the step is running.
 *  Returns null when not running or no startTime.
 */
export function useElapsedTime(startTime: number | undefined, isRunning: boolean): string | null {
  const [elapsed, setElapsed] = useState<number>(0)

  useEffect(() => {
    if (!isRunning || !startTime) return

    // Initial calculation
    setElapsed(Math.floor((Date.now() - startTime) / 1000))

    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [startTime, isRunning])

  if (!isRunning || !startTime) return null
  if (elapsed < 1) return "<1s"
  if (elapsed < 60) return `${elapsed}s`
  const min = Math.floor(elapsed / 60)
  const sec = elapsed % 60
  return `${min}m${sec > 0 ? `${sec}s` : ""}`
}

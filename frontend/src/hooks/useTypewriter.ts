import { useState, useEffect, useRef } from "react"

/**
 * 打字机效果 hook。
 *
 * 当 `fullText` 通过 SSE 流式增长时（累积全文），
 * 此 hook 返回逐步显示的子串，实现逐字出现的视觉效果。
 *
 * - 已显示的部分立即保持（不重置）
 * - 新增长的文本按 ~50 字符/秒的速度逐步显示
 * - 打字期间每次 tick 会更新 state，触发组件重渲染
 */
export function useTypewriter(fullText: string) {
  const [displayed, setDisplayed] = useState(fullText)
  const prevLenRef = useRef(fullText.length)
  const revealedRef = useRef(fullText.length)
  const rafRef = useRef<number | null>(null)
  const speedRef = useRef(50) // chars/sec

  useEffect(() => {
    const newLen = fullText.length
    const oldLen = prevLenRef.current

    // Text shrank or changed completely → show immediately
    if (newLen < oldLen || (newLen > 0 && oldLen > 0 && !fullText.startsWith(displayed))) {
      setDisplayed(fullText)
      revealedRef.current = newLen
      prevLenRef.current = newLen
      return
    }

    // New text arrived
    if (newLen > revealedRef.current) {
      const newChars = newLen - oldLen
      // If a large chunk arrived, speed up to catch up within ~1s
      speedRef.current = newChars > 20 ? Math.max(80, newChars) : 50
      prevLenRef.current = newLen
      // Don't update displayed here — let the RAF loop handle it
    }

    if (newLen === 0) {
      setDisplayed("")
      revealedRef.current = 0
      prevLenRef.current = 0
    }
  }, [fullText])

  useEffect(() => {
    let lastTime: number | null = null
    const tick = (time: number) => {
      if (lastTime === null) lastTime = time
      const dt = (time - lastTime) / 1000
      lastTime = time

      const target = fullText.length
      const current = revealedRef.current

      if (current >= target) {
        // Caught up — keep polling in case more text arrives
        rafRef.current = requestAnimationFrame(tick)
        return
      }

      const step = Math.max(1, Math.round(speedRef.current * dt))
      const next = Math.min(current + step, target)
      revealedRef.current = next
      setDisplayed(fullText.slice(0, next))

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [fullText])

  return displayed
}

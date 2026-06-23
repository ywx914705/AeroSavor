import { useState, useEffect, useRef } from "react"

/**
 * 打字机效果 hook。
 *
 * 当 `fullText` 通过 SSE 流式增长时（累积全文），
 * 此 hook 返回逐步显示的子串，实现逐字出现的视觉效果。
 *
 * - 已显示的部分立即保持（不重置）
 * - 新增长的文本按 ~50 字符/秒的速度逐步显示
 * - 使用 RAF + 节流（~30fps）避免高频重渲染导致的布局抖动
 */
export function useTypewriter(fullText: string) {
  const [displayed, setDisplayed] = useState(fullText)
  const prevLenRef = useRef(fullText.length)
  const revealedRef = useRef(fullText.length)
  const rafRef = useRef<number | null>(null)
  const speedRef = useRef(50) // chars/sec
  const lastRenderRef = useRef(0) // 上次触发 setState 的时间戳

  useEffect(() => {
    const newLen = fullText.length
    const oldLen = prevLenRef.current

    // Text shrank or changed completely → show immediately
    if (newLen < oldLen || (newLen > 0 && oldLen > 0 && !fullText.startsWith(displayed))) {
      setDisplayed(fullText)
      revealedRef.current = newLen
      prevLenRef.current = newLen
      lastRenderRef.current = performance.now()
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
      lastRenderRef.current = performance.now()
    }
  }, [fullText])

  useEffect(() => {
    let lastTime: number | null = null
    const RENDER_INTERVAL = 33 // ~30fps，减少重渲染频率防抖动

    const tick = (time: number) => {
      if (lastTime === null) lastTime = time
      const dt = (time - lastTime) / 1000
      lastTime = time

      const target = fullText.length
      const current = revealedRef.current

      if (current < target) {
        const step = Math.max(1, Math.round(speedRef.current * dt))
        const next = Math.min(current + step, target)
        revealedRef.current = next

        // 节流：只在间隔足够时才触发 React 重渲染
        const elapsed = time - lastRenderRef.current
        if (elapsed >= RENDER_INTERVAL || next >= target) {
          setDisplayed(fullText.slice(0, next))
          lastRenderRef.current = time
        }
      }

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [fullText])

  return displayed
}

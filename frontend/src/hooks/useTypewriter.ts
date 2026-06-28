import { useState, useEffect, useRef } from "react"

/**
 * 打字机效果 hook —— 优化版。
 *
 * 当 `fullText` 通过 SSE 流式增长时（累积全文），
 * 此 hook 返回逐步显示的子串，实现逐字出现的视觉效果。
 *
 * 优化点（相比旧版）：
 * - RAF 只在有未显示文本时才循环，追上后立即停止，零空闲开销
 * - 新文本到来时重新启动 RAF 循环
 * - 节流 ~30fps，避免高频 setState 导致布局抖动
 */
export function useTypewriter(fullText: string) {
  const [displayed, setDisplayed] = useState(fullText)
  const prevLenRef = useRef(fullText.length)
  const revealedRef = useRef(fullText.length)
  const rafRef = useRef<number | null>(null)
  const speedRef = useRef(60) // chars/sec（略提速）
  const lastRenderRef = useRef(0)
  // 用 ref 持有 fullText 最新值，避免 RAF tick 闭包拿到旧值
  const fullTextRef = useRef(fullText)
  fullTextRef.current = fullText

  // 启动 RAF 循环（只在有未显示文本时调用）
  const startLoop = useRef(() => {})
  startLoop.current = () => {
    // 如果已有 RAF 在跑，不重复启动
    if (rafRef.current !== null) return

    let lastTime: number | null = null
    const RENDER_INTERVAL = 67 // ~15fps — sufficient for typing feel, halves layout thrash

    const tick = (time: number) => {
      if (lastTime === null) lastTime = time
      const dt = (time - lastTime) / 1000
      lastTime = time

      const target = fullTextRef.current.length
      const current = revealedRef.current

      if (current < target) {
        const step = Math.max(1, Math.round(speedRef.current * dt))
        const next = Math.min(current + step, target)
        revealedRef.current = next

        // 节流：只在间隔足够时才触发 React 重渲染
        const elapsed = time - lastRenderRef.current
        if (elapsed >= RENDER_INTERVAL || next >= target) {
          setDisplayed(fullTextRef.current.slice(0, next))
          lastRenderRef.current = time
        }

        // 还有未显示文本 → 继续
        rafRef.current = requestAnimationFrame(tick)
      } else {
        // 已追上 → 停止循环，释放主线程
        rafRef.current = null
      }
    }

    rafRef.current = requestAnimationFrame(tick)
  }

  useEffect(() => {
    const newLen = fullText.length
    const oldLen = prevLenRef.current

    // Text shrank or changed completely → show immediately
    if (newLen < oldLen || (newLen > 0 && oldLen > 0 && !fullText.startsWith(displayed))) {
      setDisplayed(fullText)
      revealedRef.current = newLen
      prevLenRef.current = newLen
      lastRenderRef.current = performance.now()
      // 全量替换后不需要 RAF
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    // New text arrived
    if (newLen > revealedRef.current) {
      const newChars = newLen - oldLen
      // If a large chunk arrived, speed up to catch up within ~1s
      speedRef.current = newChars > 20 ? Math.max(80, newChars) : 60
      prevLenRef.current = newLen
      // 启动/恢复 RAF 循环
      startLoop.current()
    }

    if (newLen === 0) {
      setDisplayed("")
      revealedRef.current = 0
      prevLenRef.current = 0
      lastRenderRef.current = performance.now()
    }
  }, [fullText])

  // 卸载时清理 RAF
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  return displayed
}

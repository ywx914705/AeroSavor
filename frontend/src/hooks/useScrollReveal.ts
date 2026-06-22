import { useEffect, useRef } from "react"

/**
 * 轻量滚动显示 hook — IntersectionObserver 驱动
 * 给 ref 元素自动添加 "revealed" 类，配合 CSS scroll-reveal 系列类使用
 */
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>(
  options?: { threshold?: number; rootMargin?: string; once?: boolean }
) {
  const ref = useRef<T>(null)
  const { threshold = 0.15, rootMargin = "0px 0px -60px 0px", once = true } = options || {}

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed")
            if (once) observer.unobserve(entry.target)
          } else if (!once) {
            entry.target.classList.remove("revealed")
          }
        }
      },
      { threshold, rootMargin }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [threshold, rootMargin, once])

  return ref
}

/**
 * 批量滚动显示 — 用于列表/网格
 * 返回一个 callback ref，自动为每个元素添加延迟和 IntersectionObserver
 */
export function useScrollRevealGroup(options?: {
  threshold?: number
  rootMargin?: string
  stagger?: number
}) {
  const { threshold = 0.1, rootMargin = "0px 0px -40px 0px", stagger = 80 } = options || {}

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            const delay = i * stagger
            setTimeout(() => entry.target.classList.add("revealed"), delay)
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold, rootMargin }
    )

    const elements = document.querySelectorAll(".scroll-reveal-group")
    elements.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [threshold, rootMargin, stagger])
}

import { memo, useRef, useCallback, useState, useEffect, type MouseEvent } from "react"
import type { Restaurant } from "../../api/client"

interface Props {
  restaurant: Restaurant
  rank: number
  sessionId: string
  onFeedback: (poiId: string, poiName: string, action: string) => void
  onToggleFavorite: (poiId: string, poiName: string) => void
  isFav: boolean
  index: number
}

/** Enhanced count-up with spring physics */
function CountUpNumber({ value, suffix = "" }: { value: string; suffix?: string }) {
  const [display, setDisplay] = useState("0")
  const [done, setDone] = useState(false)

  useEffect(() => {
    const num = parseFloat(value)
    if (isNaN(num)) { setDisplay(value); setDone(true); return }
    const duration = 1000
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      // Spring easing for more dynamic feel
      const eased = progress < 0.5
        ? 4 * progress * progress * progress
        : 1 - Math.pow(-2 * progress + 2, 3) / 2
      setDisplay((num * eased).toFixed(1))
      if (progress < 1) requestAnimationFrame(tick)
      else setDone(true)
    }
    requestAnimationFrame(tick)
  }, [value])

  return <>{display}{suffix}</>
}

function RecommendCardInner({
  restaurant: r,
  rank,
  onFeedback,
  onToggleFavorite,
  isFav,
  index,
}: Props) {
  const ratingStr = r.rating > 0 ? r.rating.toFixed(1) : "—"
  const costStr = r.cost > 0 ? String(r.cost) : "—"
  const distLabel = r.distance >= 1000 ? `${(r.distance / 1000).toFixed(1)}km` : `${r.distance}m`
  const delay = 150 + index * 140
  const isTopRank = rank <= 3
  const cardRef = useRef<HTMLElement>(null)
  const rafRef = useRef<number>(0)
  const [isVisible, setIsVisible] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  const [isPressed, setIsPressed] = useState(false)
  const [ripplePos, setRipplePos] = useState<{ x: number; y: number } | null>(null)

  // IntersectionObserver for scroll-triggered entrance
  useEffect(() => {
    const el = cardRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.15 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Enhanced 3D tilt + spotlight glow
  const handleMouseMove = useCallback((e: MouseEvent<HTMLElement>) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => {
      const card = cardRef.current
      if (!card) return
      const rect = card.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const centerX = rect.width / 2
      const centerY = rect.height / 2
      // More dramatic tilt for premium feel
      const rotateX = ((y - centerY) / centerY) * -5
      const rotateY = ((x - centerX) / centerX) * 5
      const scale = 1 + (1 - Math.abs(x - centerX) / centerX) * 0.02
      card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px) scale(${scale})`
      card.style.setProperty("--spot-x", `${x}px`)
      card.style.setProperty("--spot-y", `${y}px`)
    })
  }, [])

  const handleMouseLeave = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    const card = cardRef.current
    if (card) {
      card.style.transform = "perspective(800px) rotateX(0deg) rotateY(0deg) translateY(0px) scale(1)"
    }
    setIsHovered(false)
  }, [])

  // Ripple effect on click
  const handleRipple = useCallback((e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setRipplePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    })
    setTimeout(() => setRipplePos(null), 600)
  }, [])

  return (
    <article
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onMouseDown={() => setIsPressed(true)}
      onMouseUp={() => setIsPressed(false)}
      onClick={handleRipple}
      className="rounded-2xl overflow-hidden bg-white border border-slate-100/80
        mb-6 spotlight-card
        transition-all duration-700 ease-out
        hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),0_15px_30px_rgba(0,0,0,0.04)]
        hover:border-amber-100/60
        hover:scale-[1.01]"
      style={{
        animationDelay: `${delay}ms`,
        transformStyle: "preserve-3d",
        willChange: "transform",
        opacity: isVisible ? 1 : 0,
        transform: isVisible
          ? isPressed
            ? "perspective(800px) rotateX(0deg) rotateY(0deg) translateY(-2px) scale(0.98)"
            : "translateY(0) scale(1)"
          : "translateY(60px) scale(0.9) rotateX(10deg)",
        filter: isVisible ? "blur(0)" : "blur(8px)",
        transition: "opacity 0.8s cubic-bezier(0.22, 1, 0.36, 1), transform 0.8s cubic-bezier(0.22, 1, 0.36, 1), filter 0.8s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.7s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.7s cubic-bezier(0.22, 1, 0.36, 1)",
      }}
    >
      {/* Photo strip */}
      {r.photos && r.photos.length > 0 ? (
        <div className="relative overflow-hidden group">
          <div className="flex photo-strip overflow-x-auto snap-x snap-mandatory">
            {r.photos.slice(0, 3).map((url, i) => (
              <div key={i} className="w-full shrink-0 snap-center relative overflow-hidden">
                <img
                  src={url}
                  alt={`${r.name} ${i + 1}`}
                  className="w-full h-48 md:h-60 object-cover photo-zoom transition-transform duration-700 ease-out"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
          {/* Enhanced gradient overlays */}
          <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-black/40 via-black/15 to-transparent pointer-events-none" />
          <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-black/20 via-black/5 to-transparent pointer-events-none" />
          {/* Shimmer overlay on hover */}
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />

          {r.photos.length > 1 && (
            <div className="absolute bottom-3 right-3 bg-white/95 backdrop-blur-md rounded-full px-3 py-1.5 text-[11px] text-slate-700 font-semibold shadow-lg">
              1/{Math.min(r.photos.length, 3)}
            </div>
          )}
          {/* Rank badge with enhanced glow */}
          <div className="absolute top-3 left-3">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2
              bg-white/95 backdrop-blur-md shadow-lg text-xs font-bold
              ${isTopRank ? "animate-rank-glow ring-2 ring-amber-200/50" : ""}`}
              style={{
                animation: isVisible ? `badge-float 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) ${delay + 100}ms both` : undefined,
              }}>
              {isTopRank && <span className="text-sm">{rank === 1 ? "🥇" : rank === 2 ? "🥈" : "🥉"}</span>}
              <span className="text-gradient-amber font-black">#{rank}</span>
            </span>
          </div>
          {/* Favorite with enhanced animation */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleFavorite(r.id, r.name)
              const btn = e.currentTarget
              btn.classList.remove("animate-heart-pop")
              void btn.offsetWidth
              btn.classList.add("animate-heart-pop")
            }}
            className={`absolute top-3 right-3 w-10 h-10 rounded-full flex items-center justify-center text-lg
              transition-all duration-400 shadow-lg
              ${isFav
                ? "bg-amber-500 text-white scale-100 shadow-amber-500/40 ring-2 ring-amber-300/50"
                : "bg-white/95 backdrop-blur-md text-slate-400 hover:bg-amber-500 hover:text-white hover:scale-110 hover:shadow-amber-500/30"
              }`}
            aria-label={isFav ? "取消收藏" : "收藏"}
          >
            {isFav ? "♥" : "♡"}
          </button>
        </div>
      ) : (
        <div className="h-32 bg-gradient-to-br from-slate-50 via-white to-slate-50/50
          flex items-center justify-between px-6 relative overflow-hidden group">
          {/* Enhanced pattern overlay */}
          <div className="absolute inset-0 opacity-[0.04]"
            style={{ backgroundImage: "radial-gradient(circle at 1px 1px, #F59E0B 1px, transparent 0)", backgroundSize: "16px 16px" }} />
          {/* Shimmer overlay */}
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="flex items-center gap-4 relative z-10">
            <span className="text-xl font-black text-gradient-amber">
              {isTopRank && <span className="text-base mr-1.5">{rank === 1 ? "🥇" : rank === 2 ? "🥈" : "🥉"}</span>}
              #{rank}
            </span>
            <div>
              <h3 className="text-lg font-bold text-slate-900">{r.name}</h3>
              {(r.type || r.suitable_for) && (
                <span className="text-xs text-slate-500 font-medium">
                  {r.type}{r.type && r.suitable_for ? " · " : ""}{r.suitable_for}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleFavorite(r.id, r.name)
              const btn = e.currentTarget
              btn.classList.remove("animate-heart-pop")
              void btn.offsetWidth
              btn.classList.add("animate-heart-pop")
            }}
            className={`w-10 h-10 rounded-full flex items-center justify-center text-lg
              transition-all duration-400
              ${isFav
                ? "bg-amber-500 text-white shadow-lg shadow-amber-500/30 ring-2 ring-amber-300/50"
                : "bg-white text-slate-400 hover:bg-amber-500 hover:text-white hover:scale-110 hover:shadow-lg hover:shadow-amber-500/30"
              }`}
          >
            {isFav ? "♥" : "♡"}
          </button>
        </div>
      )}

      {/* Info section with enhanced transitions */}
      <div className="px-5 py-4">
        {r.photos && r.photos.length > 0 && (
          <div className="mb-3">
            <h3 className="text-lg font-bold text-slate-900 mb-0.5">{r.name}</h3>
            {(r.type || r.suitable_for) && (
              <span className="text-xs text-slate-500 font-medium">
                {r.type}{r.type && r.suitable_for ? " · " : ""}{r.suitable_for}
              </span>
            )}
          </div>
        )}

        {/* Data pills with enhanced stagger and pop-in */}
        <div className={`flex items-center gap-2 flex-wrap ${isVisible ? "stagger-wave" : "opacity-0"}`}>
          <span className="inline-flex items-center gap-1.5 bg-gradient-to-br from-amber-50 to-orange-50 text-amber-700
            px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm shadow-amber-100/60 border border-amber-100/60
            transition-all duration-300 hover:scale-105 hover:shadow-amber-200/60">
            ★ <CountUpNumber value={ratingStr} />
          </span>
          <span className="inline-flex items-center gap-1.5 bg-orange-50 text-orange-700
            px-3 py-1.5 rounded-xl text-xs font-bold border border-orange-100/60
            transition-all duration-300 hover:scale-105 hover:shadow-md">
            ¥{costStr}/人
          </span>
          <span className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700
            px-3 py-1.5 rounded-xl text-xs font-bold border border-emerald-100/60
            transition-all duration-300 hover:scale-105 hover:shadow-md">
            {distLabel}
          </span>
          {r.suitable_for && (
            <span className="inline-flex items-center gap-1.5 bg-slate-50 text-slate-600
              px-3 py-1.5 rounded-xl text-xs font-semibold border border-slate-100/80
              transition-all duration-300 hover:scale-105 hover:shadow-md">
              {r.suitable_for}
            </span>
          )}
        </div>

        {r.highlight && (
          <p className="mt-4 text-sm font-bold text-amber-700 leading-relaxed
            pl-4 border-l-[3px] border-amber-400 bg-gradient-to-r from-amber-50/60 to-transparent
            py-2 pr-4 rounded-r-xl shadow-sm shadow-amber-100/40">
            {r.highlight}
          </p>
        )}

        {r.reason && (
          <p className="mt-3 text-sm leading-6 text-slate-600">{r.reason}</p>
        )}

        {r.address && (
          <p className="mt-3 text-xs text-slate-400 truncate flex items-center gap-2 hover:text-slate-600 transition-colors duration-200">
            <svg width="12" height="12" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
              <path d="M5 1a3 3 0 013 3c0 2.25-3 5-3 5S2 6.25 2 4a3 3 0 013-3z" />
              <circle cx="5" cy="4" r="1" />
            </svg>
            {r.address}
          </p>
        )}
      </div>

      {/* Enhanced action buttons with ripple */}
      <div className="flex border-t border-slate-100/80 relative">
        {ripplePos && (
          <div
            className="absolute rounded-full bg-amber-400/20 pointer-events-none animate-ping"
            style={{
              left: ripplePos.x - 20,
              top: ripplePos.y - 20,
              width: 40,
              height: 40,
            }}
          />
        )}
        <a
          href={`https://uri.amap.com/navigation?to=${r.location}&name=${encodeURIComponent(r.name)}&mode=car&policy=1`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onFeedback(r.id, r.name, "navigated")}
          className="flex-1 h-12 bg-gradient-to-r from-amber-500 via-amber-400 to-orange-500 text-white text-xs font-bold
            flex items-center justify-center gap-2
            hover:from-amber-600 hover:via-amber-500 hover:to-orange-600 transition-all duration-400
            active:scale-[0.97] relative overflow-hidden group"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/15 to-white/0 translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-1000" />
          <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="group-hover:scale-110 transition-transform duration-300">
            <path d="M6 2v3M6 7v3M2 6h3M7 6h3" />
          </svg>
          导航前往
        </a>
        <a
          href={r.amap_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onFeedback(r.id, r.name, "clicked")}
          className="px-6 border-l border-slate-100/80 text-xs font-semibold
            flex items-center justify-center gap-1.5 text-slate-500
            hover:text-amber-600 hover:bg-amber-50/60 transition-all duration-300
            hover:shadow-inner"
        >
          详情
          <svg width="8" height="8" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
            className="group-hover:translate-x-0.5 transition-transform duration-300">
            <path d="M3 1l3 3-3 3" />
          </svg>
        </a>
        <button
          onClick={() => onFeedback(r.id, r.name, "disliked")}
          className="px-4 border-l border-slate-100/80 text-xs
            flex items-center justify-center text-slate-400
            hover:text-red-500 hover:bg-red-50/60 transition-all duration-300
            active:scale-95 hover:shadow-inner"
          aria-label="不感兴趣"
        >
          <svg width="15" height="15" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>
    </article>
  )
}

/** memo 化：餐厅数据/收藏状态不变时跳过重渲，避免流式 token 更新连带重绘所有卡片 */
export const RecommendCard = memo(RecommendCardInner, (prev, next) => {
  return prev.restaurant.id === next.restaurant.id
    && prev.isFav === next.isFav
    && prev.rank === next.rank
})

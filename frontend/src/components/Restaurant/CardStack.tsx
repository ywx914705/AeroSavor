import { memo } from "react"
import type { Restaurant } from "../../api/client"
import { RecommendCard } from "./RecommendCard"

interface Props {
  restaurants: Restaurant[]
  sessionId: string
  onFeedback: (poiId: string, poiName: string, action: string) => void
  onToggleFavorite: (poiId: string, poiName: string) => void
  favoriteIds: Set<string>
}

function CardStackInner({
  restaurants,
  sessionId,
  onFeedback,
  onToggleFavorite,
  favoriteIds,
}: Props) {
  if (!restaurants.length) return null

  const display = restaurants.slice(0, 5)
  const total = restaurants.length

  return (
    <section className="mt-10">
      {/* Section header */}
      <div className="flex items-end justify-between pb-4 mb-6 animate-reveal-blur">
        <div>
          <span className="block text-[11px] text-slate-400 tracking-[0.15em] uppercase font-bold">精选推荐</span>
          <h2 className="text-2xl md:text-3xl font-black tracking-tight mt-1.5 text-slate-900">
            为你推荐
          </h2>
        </div>
        <div className="flex items-center gap-1.5 bg-white px-3 py-1.5 rounded-full border border-slate-200/60">
          <span className="text-sm font-black text-gradient-amber">
            {Math.min(total, 5)}
          </span>
          <span className="text-xs text-slate-400">/{total}</span>
        </div>
      </div>

      {/* Cards */}
      {display.map((r, i) => (
        <RecommendCard
          key={r.id || i}
          restaurant={r}
          rank={i + 1}
          sessionId={sessionId}
          onFeedback={onFeedback}
          onToggleFavorite={onToggleFavorite}
          isFav={favoriteIds.has(r.id)}
          index={i}
        />
      ))}

      {total > 5 && (
        <div className="pt-4 text-center animate-reveal-blur">
          <p className="text-sm text-slate-400">
            还有 <span className="font-bold text-gradient-amber">{total - 5}</span> 家餐厅
          </p>
          <p className="text-xs text-slate-300 mt-1.5">继续描述你的需求来缩小范围</p>
        </div>
      )}
    </section>
  )
}

/** memo 化：推荐列表和收藏状态不变时跳过重渲 */
export const CardStack = memo(CardStackInner, (prev, next) => {
  if (prev.restaurants.length !== next.restaurants.length) return false
  if (prev.favoriteIds !== next.favoriteIds) return false
  // 浅比 restaurants id 列表
  for (let i = 0; i < prev.restaurants.length; i++) {
    if (prev.restaurants[i].id !== next.restaurants[i].id) return false
  }
  return true
})

/** Empty results state */
export function EmptyResults({ onRetry }: { onRetry: (query: string) => void }) {
  return (
    <div className="mt-10 rounded-2xl bg-white border border-slate-100/80 p-8 text-center animate-reveal-blur
      shadow-sm">
      <div className="text-5xl mb-4">🔍</div>
      <h3 className="text-lg font-bold text-slate-900 mb-2">没有找到合适的餐厅</h3>
      <p className="text-sm text-slate-500 mb-6 max-w-sm mx-auto leading-relaxed">
        可能附近没有符合条件的餐厅，试试放宽条件或换个区域？
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {["附近好吃的", "换个区域", "不限价格"].map((q) => (
          <button
            key={q}
            onClick={() => onRetry(q)}
            className="px-3.5 py-1.5 text-xs rounded-full bg-slate-50 text-slate-600 border border-slate-100
              hover:border-amber-200 hover:text-amber-600 hover:bg-amber-50/50
              transition-all duration-200"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}

interface RouteInfo {
  walking?: { mode: string; duration_min: number; distance_m: number } | null
  driving?: { mode: string; duration_min: number; distance_m: number; tolls?: number } | null
  transit?: { mode: string; duration_min: number; distance_m: number; cost?: number } | null
  nav_url?: string
  destination_name?: string
}

interface Props {
  route: RouteInfo
  destinationName?: string
}

function formatDistance(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(1)}km`
  return `${m}m`
}

export function RoutePanel({ route, destinationName }: Props) {
  if (!route || (!route.walking && !route.driving && !route.transit)) {
    return null
  }

  const items: Array<{
    mode: string; duration_min: number; distance_m: number;
    icon: string; bg: string; text: string;
    tolls?: number | null; cost?: number | null;
  }> = [
    route.walking && { ...route.walking, icon: "🚶", bg: "bg-emerald-50", text: "text-emerald-600" },
    route.driving && { ...route.driving, icon: "🚗", bg: "bg-amber-50", text: "text-amber-600" },
    route.transit && { ...route.transit, icon: "🚌", bg: "bg-blue-50", text: "text-blue-600" },
  ].filter(Boolean) as any[]

  const fastestIdx = items.reduce((min, item, i) =>
    item.duration_min < items[min].duration_min ? i : min, 0)

  return (
    <div className="rounded-2xl overflow-hidden bg-white border border-slate-100/80 shadow-sm mb-5 animate-reveal-blur
      hover:shadow-md transition-shadow duration-300">
      {/* Header */}
      <div className="px-4 py-3.5 border-b border-slate-50 bg-gradient-to-r from-slate-50/50 to-transparent">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">路线规划</span>
            {(destinationName || route.destination_name) && (
              <h4 className="font-bold text-sm mt-0.5 text-slate-900">
                {destinationName || route.destination_name}
              </h4>
            )}
          </div>
          <span className="text-xs text-amber-600 font-bold bg-amber-50 px-2.5 py-1 rounded-full border border-amber-100/60">
            {items.length} 种方案
          </span>
        </div>
      </div>

      {/* Routes */}
      <div className="divide-y divide-slate-50">
        {items.map((item, i) => {
          const isFastest = i === fastestIdx && items.length > 1
          return (
            <div
              key={i}
              className={`flex items-center px-4 py-3.5 gap-3
                transition-all duration-300 hover:bg-slate-50/50
                animate-slide-in-left ${isFastest ? "bg-gradient-to-r from-amber-50/40 to-transparent" : ""}`}
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className={`${item.bg} w-11 h-11 rounded-xl flex items-center justify-center text-lg shrink-0
                border border-white/80 shadow-sm`}>
                {item.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-slate-500 font-semibold">{item.mode}</span>
                  {isFastest && (
                    <span className="text-[10px] text-amber-700 font-bold bg-amber-100 px-2 py-0.5 rounded-full">
                      最快
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-1.5 mt-0.5">
                  <span className="text-xl font-black text-slate-900 tabular">
                    {item.duration_min}
                  </span>
                  <span className="text-xs text-slate-400 font-medium">分钟</span>
                  <span className="text-xs text-slate-200 ml-1">·</span>
                  <span className="text-xs text-slate-400 ml-1 font-medium">{formatDistance(item.distance_m)}</span>
                </div>
              </div>
              {item.tolls != null && item.tolls > 0 && (
                <span className="text-xs text-orange-600 bg-orange-50 px-2.5 py-1 rounded-full font-bold border border-orange-100/60">
                  过路费 ¥{item.tolls}
                </span>
              )}
              {item.cost != null && item.cost > 0 && (
                <span className="text-xs text-orange-600 bg-orange-50 px-2.5 py-1 rounded-full font-bold border border-orange-100/60">
                  ¥{item.cost}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* CTA */}
      {route.nav_url && (
        <a
          href={route.nav_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 h-11 bg-gradient-to-r from-amber-500 to-orange-500 text-white text-sm font-bold
            hover:from-amber-600 hover:to-orange-600 transition-all duration-300 active:scale-[0.99] relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 translate-x-[-200%] hover:translate-x-[200%] transition-transform duration-700" />
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M7 2v4M7 8v4M2 7h4M8 7h4" />
          </svg>
          打开高德导航
        </a>
      )}
    </div>
  )
}

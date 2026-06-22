import { useState, useEffect, useRef, useCallback } from "react"
import { AeroSavorIcon } from "../../assets/Logo"

const TAGLINES = [
  "多智能体协同，精准推荐",
  "理解你的口味，发现美味",
  "实时数据驱动，品质保障",
]

function getGreeting(): { text: string; sub: string } {
  const h = new Date().getHours()
  if (h < 6) return { text: "夜深了，来点暖胃的", sub: "推荐附近的粥铺和夜宵" }
  if (h < 9) return { text: "早安，美好的一天从早餐开始", sub: "包子铺、豆浆油条还是咖啡店？" }
  if (h < 11) return { text: "上午好，来杯咖啡？", sub: "附近的咖啡馆和早午餐" }
  if (h < 13) return { text: "午餐时间到", sub: "附近评分最高的餐厅" }
  if (h < 17) return { text: "下午茶时间", sub: "甜品店和咖啡馆推荐" }
  if (h < 19) return { text: "今天吃什么好呢", sub: "根据你的口味智能推荐" }
  if (h < 21) return { text: "晚餐时间到了", sub: "为你精选附近的美食" }
  return { text: "夜深了，来点暖胃的", sub: "粥铺、面馆、烧烤... 夜宵安排上" }
}

const CATEGORIES = [
  { label: "附近好吃的", query: "附近好吃的", emoji: "🍽️", accent: "#F59E0B", bg: "from-amber-50 to-orange-50/60", border: "border-amber-200/60", text: "text-amber-800" },
  { label: "日料", query: "日料 人均150以内", emoji: "🍣", accent: "#F43F5E", bg: "from-rose-50 to-pink-50/60", border: "border-rose-200/60", text: "text-rose-800" },
  { label: "川菜", query: "评分高的川菜", emoji: "🌶️", accent: "#EF4444", bg: "from-red-50 to-orange-50/60", border: "border-red-200/60", text: "text-red-800" },
  { label: "火锅", query: "附近的火锅", emoji: "🫕", accent: "#F97316", bg: "from-orange-50 to-red-50/60", border: "border-orange-200/60", text: "text-orange-800" },
  { label: "烤鸭", query: "附近的烤鸭", emoji: "🦆", accent: "#EAB308", bg: "from-yellow-50 to-amber-50/60", border: "border-yellow-200/60", text: "text-yellow-800" },
  { label: "烧烤", query: "附近的烧烤", emoji: "🍢", accent: "#78716C", bg: "from-stone-50 to-amber-50/60", border: "border-stone-200/60", text: "text-stone-800" },
]

const QUICK_ITEMS = [
  { name: "咖啡", emoji: "☕" },
  { name: "甜品", emoji: "🧁" },
  { name: "面馆", emoji: "🍜" },
  { name: "小龙虾", emoji: "🦞" },
  { name: "奶茶", emoji: "🧋" },
  { name: "披萨", emoji: "🍕" },
]

/** Orbit ring around the logo */
function OrbitRing({ radius, duration, color, dotSize, delay }: {
  radius: number; duration: number; color: string; dotSize: number; delay: number
}) {
  return (
    <div
      className="absolute left-1/2 top-1/2 rounded-full pointer-events-none"
      style={{
        width: radius * 2,
        height: radius * 2,
        marginLeft: -radius,
        marginTop: -radius,
        border: `1px solid ${color}20`,
        animation: `orbit-spin ${duration}s linear infinite`,
        animationDelay: `${delay}s`,
      }}
    >
      <div
        className="absolute rounded-full"
        style={{
          width: dotSize,
          height: dotSize,
          background: color,
          top: -dotSize / 2,
          left: "50%",
          marginLeft: -dotSize / 2,
          boxShadow: `0 0 ${dotSize * 2}px ${color}80, 0 0 ${dotSize}px ${color}60`,
        }}
      />
    </div>
  )
}

export function HeroSection({ onSend }: { onSend: (q: string) => void }) {
  const greeting = getGreeting()
  const [taglineIdx, setTaglineIdx] = useState(0)
  const [visible, setVisible] = useState(false)
  const [typedText, setTypedText] = useState("")
  const fullText = "告诉我你想吃什么"
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  useEffect(() => {
    const id = setInterval(() => setTaglineIdx((i) => (i + 1) % TAGLINES.length), 3500)
    return () => clearInterval(id)
  }, [])

  // Typewriter
  useEffect(() => {
    let idx = 0
    let running = true
    const type = () => {
      if (!running) return
      if (idx <= fullText.length) {
        setTypedText(fullText.slice(0, idx))
        idx++
        timerRef.current = setTimeout(type, 70 + Math.random() * 50)
      } else {
        timerRef.current = setTimeout(() => { idx = 0; type() }, 2500)
      }
    }
    timerRef.current = setTimeout(type, 800)
    return () => { running = false; clearTimeout(timerRef.current) }
  }, [])

  const focusInput = useCallback(() => {
    (document.querySelector('textarea[aria-label="输入消息"]') as HTMLTextAreaElement)?.focus()
  }, [])

  // Unified reveal style
  const reveal = (delay: number) => ({
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(20px)",
    transition: `opacity 0.5s cubic-bezier(0.22,1,0.36,1) ${delay}ms, transform 0.5s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
  })

  return (
    <div className="flex-1 flex flex-col overflow-y-auto overflow-x-hidden bg-transparent relative">
      <div className="relative z-10 flex flex-col items-center pt-1.5 pb-1 px-6">

        {/* ── Logo with orbit rings ── */}
        <div className="relative mb-1" style={{ width: 80, height: 80 }}>
          {/* Subtle aura */}
          <div className="absolute inset-[-30%] rounded-full bg-slate-200/30 blur-[50px] pointer-events-none" />

          {/* Orbit rings */}
          <OrbitRing radius={32} duration={10} color="#94A3B8" dotSize={4} delay={0} />
          <OrbitRing radius={39} duration={16} color="#CBD5E1" dotSize={3} delay={-3} />

          {/* Center logo */}
          <div className="absolute left-1/2 top-1/2 z-10" style={{
            opacity: visible ? 1 : 0,
            transform: `translate(-50%, -50%) scale(${visible ? 1 : 0.5})`,
            transition: "all 0.7s cubic-bezier(0.34,1.56,0.64,1) 0.15s",
          }}>
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-amber-400 via-orange-400 to-orange-500
              flex items-center justify-center shadow-xl shadow-amber-500/30
              ring-1 ring-white/20 hover:scale-110 transition-transform duration-500">
              <AeroSavorIcon size={22} />
            </div>
          </div>
        </div>

        {/* ── Brand name — LARGE, using inline style to guarantee size ── */}
        <h1 style={reveal(200)}>
          <span style={{
            fontSize: "clamp(32px, 6vw, 46px)",
            fontWeight: 900,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            display: "inline-flex",
          }}>
            <span className="hero-title-gradient">Aero</span>
            <span style={{ color: "#0f172a" }}>Savor</span>
          </span>
        </h1>

        {/* ── Tagline ── */}
        <div className="mt-1.5 h-5 flex items-center justify-center overflow-hidden" style={reveal(350)}>
          <p
            className="text-gradient-flow font-bold tracking-[0.15em] uppercase"
            style={{ fontSize: "12px" }}
            key={taglineIdx}
          >
            {TAGLINES[taglineIdx]}
          </p>
        </div>

        {/* ── Greeting ── */}
        <div className="mt-2 text-center" style={reveal(450)}>
          <p style={{ fontSize: "20px", fontWeight: 800, color: "#1e293b", letterSpacing: "-0.01em" }}>
            {greeting.text}
          </p>
          <p className="text-slate-400 mt-1.5 font-medium" style={{ fontSize: "13px" }}>{greeting.sub}</p>
        </div>

        {/* ── Search prompt ── */}
        <div className="flow-border active w-full mt-2" style={{ maxWidth: 460, ...reveal(600) }}>
          <div
            className="relative flex items-center gap-3 px-5 py-3 rounded-2xl glass-strong
              shadow-lg shadow-black/[0.04] cursor-pointer
              hover:shadow-xl transition-all duration-400 group input-glow-premium"
            onClick={focusInput}
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 via-orange-400 to-orange-500
              flex items-center justify-center shadow-md shadow-amber-500/25
              group-hover:shadow-lg group-hover:scale-105 transition-all duration-300 shrink-0">
              <AeroSavorIcon size={18} />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-slate-400 font-semibold block" style={{ fontSize: "13px" }}>
                {typedText}<span className="glow-typing-cursor" />
              </span>
            </div>
            <span className="text-slate-300 font-bold px-2 py-1 rounded-md bg-slate-50 border border-slate-100 shrink-0" style={{ fontSize: "10px" }}>
              Enter ↵
            </span>
          </div>
        </div>
      </div>

      {/* ── Category grid ── */}
      <div className="px-5 md:px-8 pb-2 relative z-10">
        <div style={{ maxWidth: 460, margin: "0 auto" }}>
          <div className="flex items-center gap-2 mb-2" style={reveal(700)}>
            <span className="font-bold text-slate-400 uppercase tracking-[0.15em]" style={{ fontSize: "11px" }}>
              发现美食
            </span>
            <div className="flex-1 h-px bg-gradient-to-r from-slate-200 to-transparent" />
          </div>

          <div className="grid grid-cols-3 gap-2">
            {CATEGORIES.map((cat, i) => (
              <button
                key={cat.label}
                onClick={() => onSend(cat.query)}
                className="group relative flex flex-col items-center gap-1 py-2.5 px-2 rounded-2xl
                  bg-gradient-to-br border overflow-hidden
                  hover:shadow-xl hover:scale-[1.04] hover:-translate-y-1
                  transition-all duration-400 category-shimmer magnetic-hover
                  focus:outline-none focus:ring-2 focus:ring-amber-300/50"
                style={{
                  ...reveal(750 + i * 50),
                  borderColor: "rgba(226, 232, 240, 0.6)",
                  background: "white",
                }}
                onMouseMove={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  const x = ((e.clientX - rect.left) / rect.width - 0.5) * 6
                  const y = ((e.clientY - rect.top) / rect.height - 0.5) * 6
                  e.currentTarget.style.transform = `translate(${x}px, ${y}px) scale(1.03)`
                }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = "" }}
              >
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-400"
                  style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.06), transparent)" }} />
                <span className="group-hover:scale-125 transition-transform duration-300 relative z-10"
                  style={{ fontSize: "24px" }}>{cat.emoji}</span>
                <span className={`font-bold relative z-10 ${cat.text}`} style={{ fontSize: "12px" }}>{cat.label}</span>
              </button>
            ))}
          </div>

          {/* Feature badges — immediately visible under grid */}
          <div className="mt-3 flex items-center justify-center gap-2.5 flex-wrap" style={reveal(950)}>
            {[
              { icon: "⚡", text: "多智能体协同", accent: true },
              { icon: "📡", text: "实时餐厅数据" },
              { icon: "🗺️", text: "智能路线规划" },
            ].map((f) => (
              <div key={f.text} className="badge-enhanced">
                <span style={{ fontSize: "13px" }}>{f.icon}</span>
                {f.text}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

import { useState, KeyboardEvent, useRef, useEffect } from "react"
import { useChatStore } from "../../store/chat"

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  disabled?: boolean
}

export function InputBar({ onSend, onStop, disabled }: Props) {
  const [value, setValue] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendBtnRef = useRef<HTMLButtonElement>(null)
  const userLocation = useChatStore((s) => s.userLocation)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const [isFocused, setIsFocused] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([])
  const [charCount, setCharCount] = useState(0)

  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = "auto"
      el.style.height = Math.min(el.scrollHeight, 120) + "px"
    }
    setCharCount(value.length)
  }, [value])

  const submit = () => {
    const v = value.trim()
    if (!v || disabled) return
    setIsSubmitting(true)
    setTimeout(() => setIsSubmitting(false), 300)
    onSend(v)
    setValue("")
    if (textareaRef.current) textareaRef.current.style.height = "auto"
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleRipple = (e: React.MouseEvent<HTMLButtonElement>) => {
    const btn = sendBtnRef.current
    if (!btn) return
    const rect = btn.getBoundingClientRect()
    const newRipple = {
      id: Date.now(),
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }
    setRipples((prev) => [...prev, newRipple])
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== newRipple.id))
    }, 600)
  }

  return (
    <div className="relative z-10 px-4 md:px-6 py-5 bg-[#FAFAF8]/95 backdrop-blur-xl border-t border-slate-200/50">
      <div className="max-w-2xl mx-auto">
        {/* Input container */}
        <div className={`relative ${isFocused ? "flow-border active" : ""}`}>
          <div className={`rounded-2xl transition-all duration-500 relative z-10
            ${isStreaming
              ? "bg-white/98 border-2 border-amber-200/60 shadow-lg shadow-amber-100/30 streaming-border-active"
              : isSubmitting
              ? "bg-white border-2 border-amber-300/50 shadow-lg scale-[0.985]"
              : isFocused
              ? "bg-white border-2 border-slate-300/60 shadow-xl ring-1 ring-slate-200/30"
              : "bg-white border-2 border-slate-200/70 hover:border-slate-300/70 hover:shadow-md"
            }`}>

            {/* Status bar */}
            <div className="flex items-center justify-between px-5 pt-3 pb-1">
              <div className="flex items-center gap-2.5">
                {isStreaming && (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                  </span>
                )}
                <span className="text-[11px] text-slate-400 font-semibold tracking-wide">
                  {isStreaming
                    ? "智能体运行中..."
                    : isFocused
                    ? "输入你的美食需求..."
                    : "描述你想吃什么"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {charCount > 0 && isFocused && (
                  <span className="text-[10px] text-slate-300 font-mono tabular-nums">{charCount}</span>
                )}
                {userLocation && (
                  <span className="text-[11px] text-emerald-500 flex items-center gap-1.5 font-bold">
                    <span className="relative inline-flex items-center justify-center w-2.5 h-2.5">
                      <span className="absolute w-2.5 h-2.5 bg-emerald-400/30 rounded-full animate-pulse-ring" />
                      <span className="relative w-2 h-2 bg-emerald-500 rounded-full shadow-sm shadow-emerald-500/30" />
                    </span>
                    已定位
                  </span>
                )}
              </div>
            </div>

            {/* Input row */}
            <div className="flex items-end px-5 pb-3">
              <textarea
                ref={textareaRef}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={onKey}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                disabled={disabled}
                placeholder="例如：附近有什么好吃的？"
                rows={1}
                className="flex-1 px-0 py-2 text-sm leading-relaxed border-0 focus:outline-none
                  disabled:opacity-40 resize-none overflow-hidden min-h-[48px]
                  bg-transparent text-slate-900 placeholder:text-slate-300 font-medium"
                aria-label="输入消息"
              />
              {!isStreaming ? (
                <button
                  ref={sendBtnRef}
                  onClick={(e) => { handleRipple(e); submit() }}
                  disabled={disabled || !value.trim()}
                  className="relative m-1 px-5 py-2.5 text-xs font-bold
                    rounded-xl transition-all duration-400
                    flex-shrink-0 flex items-center gap-2 overflow-hidden
                    disabled:bg-slate-100 disabled:text-slate-300 disabled:cursor-not-allowed disabled:shadow-none
                    enabled:bg-gradient-to-r enabled:from-amber-500 enabled:via-amber-400 enabled:to-orange-500 enabled:text-white
                    enabled:shadow-lg enabled:shadow-amber-500/25
                    enabled:hover:shadow-xl enabled:hover:shadow-amber-500/35
                    enabled:hover:from-amber-600 enabled:hover:via-amber-500 enabled:hover:to-orange-600
                    enabled:active:scale-95
                    enabled:focus:outline-none enabled:focus:ring-2 enabled:focus:ring-amber-300/50 enabled:focus:ring-offset-2"
                >
                  {/* Button shimmer */}
                  <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 translate-x-[-200%] enabled:hover:translate-x-[200%] transition-transform duration-1000" />
                  {/* Ripple effects */}
                  {ripples.map((ripple) => (
                    <span
                      key={ripple.id}
                      className="absolute rounded-full bg-white/40 animate-ping pointer-events-none"
                      style={{
                        left: ripple.x - 15,
                        top: ripple.y - 15,
                        width: 30,
                        height: 30,
                      }}
                    />
                  ))}
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    className="relative z-10">
                    <path d="M1 7l10-5v10L1 7z" />
                  </svg>
                  <span className="relative z-10">发送</span>
                </button>
              ) : (
                <button
                  onClick={onStop}
                  className="m-1 px-5 py-2.5 bg-slate-800 text-white text-xs font-bold
                    rounded-xl hover:bg-slate-700
                    transition-all duration-300 active:scale-95
                    flex-shrink-0 flex items-center gap-2
                    shadow-lg shadow-slate-900/20
                    focus:outline-none focus:ring-2 focus:ring-slate-400/50 focus:ring-offset-2"
                >
                  <svg width="11" height="11" viewBox="0 0 10 10" fill="currentColor"
                    className="animate-pulse">
                    <rect x="1" y="1" width="8" height="8" rx="1.5" />
                  </svg>
                  停止
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Quick chips */}
        <div className="flex flex-wrap gap-2 mt-3.5 stagger-wave">
          {["附近好吃的", "评分高的川菜", "日料 人均150以内", "附近的火锅"].map((q) => (
            <button
              key={q}
              onClick={() => onSend(q)}
              disabled={isStreaming}
              className="px-3.5 py-2 text-[11px] rounded-lg font-semibold
                glass-strong text-slate-500 border border-slate-200/40
                hover:border-slate-300 hover:text-slate-700 hover:bg-slate-50/60 hover:shadow-md hover:-translate-y-0.5
                hover:ring-1 hover:ring-amber-200/40
                transition-all duration-400
                active:scale-95
                disabled:opacity-30 disabled:cursor-not-allowed
                focus:outline-none focus:ring-2 focus:ring-amber-300/50"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

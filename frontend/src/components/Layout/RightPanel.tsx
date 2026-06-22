import { useEffect, useState } from "react"
import { useChatStore, type ThinkingStepStatus } from "../../store/chat"
import { agentIcons, agentLabels } from "../../constants/agents"
import { AeroSavorIcon } from "../../assets/Logo"
import { useElapsedTime } from "../../hooks/useElapsedTime"

/** Rich status color system */
const statusTheme: Record<ThinkingStepStatus, {
  bg: string; border: string; text: string; dot: string; icon: string; glow: string
}> = {
  running: {
    bg: "bg-amber-50/80", border: "border-amber-300/50", text: "text-amber-700",
    dot: "bg-amber-400 animate-pulse", icon: "animate-pulse", glow: "shadow-amber-200/50",
  },
  done: {
    bg: "bg-emerald-50/40", border: "border-emerald-200/30", text: "text-emerald-600",
    dot: "bg-emerald-400", icon: "", glow: "",
  },
  error: {
    bg: "bg-red-50/80", border: "border-red-300/50", text: "text-red-600",
    dot: "bg-red-400", icon: "", glow: "shadow-red-200/50",
  },
  decision: {
    bg: "bg-indigo-50/60", border: "border-indigo-300/40", text: "text-indigo-600",
    dot: "bg-indigo-400", icon: "", glow: "shadow-indigo-200/30",
  },
  collaboration: {
    bg: "bg-teal-50/60", border: "border-teal-300/40", text: "text-teal-600",
    dot: "bg-teal-400", icon: "", glow: "shadow-teal-200/30",
  },
  delegation: {
    bg: "bg-blue-50/60", border: "border-blue-300/40", text: "text-blue-600",
    dot: "bg-blue-400", icon: "", glow: "shadow-blue-200/30",
  },
  quality_retry: {
    bg: "bg-purple-50/60", border: "border-purple-300/40", text: "text-purple-600",
    dot: "bg-purple-400", icon: "", glow: "shadow-purple-200/30",
  },
}

function AgentStatusCard({ agentKey, status, message, duration, startTime, justCompleted, index, isLast }: {
  agentKey: string
  status: ThinkingStepStatus
  message: string
  duration?: number
  startTime?: number
  justCompleted?: boolean
  index: number
  isLast: boolean
}) {
  const isRunning = status === "running"
  const isDone = status === "done"
  const isError = status === "error"
  const theme = statusTheme[status]

  // Live elapsed timer for running agents
  const elapsedText = useElapsedTime(startTime, isRunning)

  // Duration display for done agents
  const durationText = duration != null && duration > 0
    ? duration < 1000 ? `${duration}ms` : `${(duration / 1000).toFixed(1)}s`
    : null

  // Completion flash state
  const [flashActive, setFlashActive] = useState(false)
  useEffect(() => {
    if (justCompleted) {
      setFlashActive(true)
      const t = setTimeout(() => setFlashActive(false), 800)
      return () => clearTimeout(t)
    }
  }, [justCompleted])

  // Timeline connector color
  const connectorFill = isDone ? "done" : isRunning ? "running" : isError ? "error" : null

  return (
    <div className="relative">
      <div
        className={`relative flex items-start gap-3 py-2.5 px-3 rounded-xl
          transition-all duration-400 group
          ${isRunning ? `${theme.bg} ${theme.border} border shadow-sm ${theme.glow}` : ""}
          ${isError ? `${theme.bg} ${theme.border} border shadow-sm` : ""}
          ${status === "decision" ? `${theme.bg} ${theme.border} border shadow-sm` : ""}
          ${status === "collaboration" ? `${theme.bg} ${theme.border} border shadow-sm` : ""}
          ${status === "delegation" ? `${theme.bg} ${theme.border} border shadow-sm` : ""}
          ${status === "quality_retry" ? `${theme.bg} ${theme.border} border shadow-sm` : ""}
          ${isDone && !isRunning ? "opacity-45 hover:opacity-75" : ""}
          ${flashActive ? "animate-completion-flash" : ""}`}
        style={{
          animation: flashActive ? undefined : `slide-in-left 0.4s cubic-bezier(0.22,1,0.36,1) ${index * 80}ms both`,
        }}
      >
        {/* Status indicator */}
        <div className="relative z-10 shrink-0 mt-0.5">
          {isRunning ? (
            <span className={`block w-[26px] h-[26px] rounded-lg bg-white border-2 border-amber-300
              flex items-center justify-center text-[11px] shadow-md shadow-amber-200/50
              animate-glow-pulse ${theme.icon}`}>
              {agentIcons[agentKey] ?? "⚙️"}
            </span>
          ) : isDone ? (
            <span className="block w-[26px] h-[26px] rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100
              border-2 border-emerald-300 flex items-center justify-center
              shadow-sm shadow-emerald-200/40">
              <svg width="11" height="11" viewBox="0 0 8 8" fill="none" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round">
                <path d="M1.5 4l2 2 3-3.5" />
              </svg>
            </span>
          ) : isError ? (
            <span className="block w-[26px] h-[26px] rounded-lg bg-white border-2 border-red-300
              flex items-center justify-center text-[11px] shadow-sm shadow-red-200/40">
              ❌
            </span>
          ) : (
            <span className={`block w-[26px] h-[26px] rounded-lg bg-white border-2 ${theme.border}
              flex items-center justify-center text-[11px] shadow-sm`}>
              {agentIcons[agentKey] ?? "⚙️"}
            </span>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={`text-[12px] font-bold leading-tight ${theme.text}`}>
              {agentLabels[agentKey] || agentKey}
            </span>
            {isRunning && (
              <span className="flex gap-[2px] ml-0.5">
                <span className="typing-dot-premium" style={{ animationDelay: "0ms" }} />
                <span className="typing-dot-premium" style={{ animationDelay: "0.16s" }} />
                <span className="typing-dot-premium" style={{ animationDelay: "0.32s" }} />
              </span>
            )}
            {/* Live elapsed timer for running agents */}
            {isRunning && elapsedText && (
              <span className="text-[10px] text-amber-500/70 font-mono font-semibold bg-amber-100/50 px-1.5 py-0.5 rounded-md">
                {elapsedText}
              </span>
            )}
            {/* Duration display for done agents */}
            {durationText && isDone && (
              <span className="text-[10px] text-emerald-500/60 font-mono bg-emerald-50 px-1.5 py-0.5 rounded-md">
                {durationText}
              </span>
            )}
          </div>
          <p className={`text-[10px] leading-tight mt-0.5 truncate
            ${isRunning ? "text-amber-600/60" : isDone ? "text-slate-400" : isError ? "text-red-500/60" : "text-slate-500/70"}`}>
            {message}
          </p>
        </div>

        {/* Running pulse indicator */}
        {isRunning && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500 shadow-sm shadow-amber-500/40" />
            </span>
          </div>
        )}
      </div>

      {/* Timeline connector (not on last step) */}
      {!isLast && (
        <div className="timeline-connector">
          {connectorFill === "done" && <div className="timeline-connector-fill-done" />}
          {connectorFill === "running" && <div className="timeline-connector-fill-running" />}
          {connectorFill === "error" && <div className="timeline-connector-fill-error" />}
        </div>
      )}
    </div>
  )
}

export function RightPanel() {
  const {
    thinkingSteps,
    recommendations,
    isStreaming,
    messages,
    favoriteIds,
    lastSSEEventAt,
    hasError,
  } = useChatStore()

  const doneCount = thinkingSteps.filter((s) => s.status === "done").length
  const total = thinkingSteps.length
  const allDone = total > 0 && doneCount === total
  const hasActivity = thinkingSteps.length > 0 || recommendations.length > 0
  const statusLabel = isStreaming ? "协同运行中" : allDone ? "已完成" : hasActivity ? "处理中..." : "待命中"
  const statusStyle = isStreaming ? "status-pill-active" : allDone ? "status-pill-success" : hasActivity ? "status-pill-active" : "status-pill-idle"

  const userMsgCount = messages.filter((m) => m.role === "user").length

  // Progress: never decrease (use max of doneCount/total and previous)
  const progressPct = total > 0 ? Math.round((doneCount / total) * 100) : 0

  // SSE connection health
  const [sseHealthy, setSseHealthy] = useState(true)
  useEffect(() => {
    if (!isStreaming) { setSseHealthy(true); return }
    const check = () => {
      const lastAt = useChatStore.getState().lastSSEEventAt
      if (!lastAt) { setSseHealthy(false); return }
      setSseHealthy(Date.now() - lastAt < 35000)
    }
    check()
    const interval = setInterval(check, 5000)
    return () => clearInterval(interval)
  }, [isStreaming])

  return (
    <aside className="w-[280px] shrink-0 h-full flex flex-col bg-[#FAFAF8]/95 backdrop-blur-xl border-l border-slate-200/50">

      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-3 border-b border-slate-200/50">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 via-orange-400 to-orange-500
              flex items-center justify-center shadow-lg shadow-amber-500/25
              transition-transform duration-300 hover:scale-110">
              <AeroSavorIcon size={18} />
            </div>
            {isStreaming && (
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
                animate-ping opacity-20" />
            )}
          </div>
          <div>
            <span className="text-[14px] font-bold text-slate-900 block">协作状态</span>
          </div>
        </div>

        {/* Status pill */}
        <div className="flex items-center gap-2 mt-2.5">
          {!sseHealthy && isStreaming ? (
            <span className="status-pill-warning">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
              重连中...
            </span>
          ) : (
            <span className={`status-pill ${statusStyle}`}>
              {isStreaming ? (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                </span>
              ) : (
                <span className={`w-2 h-2 rounded-full ${allDone ? "bg-emerald-500" : hasActivity ? "bg-amber-400" : "bg-slate-300"}`} />
              )}
              {statusLabel}
            </span>
          )}
        </div>
      </div>

      {/* ── Scrollable content ── */}
      <div className="flex-1 overflow-y-auto">

        {/* ── Session stats ── */}
        <div className="px-4 py-3 border-b border-slate-200/50">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-[0.18em]">本次对话</span>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div className="rounded-xl px-3 py-2.5 text-center
              bg-white border border-slate-100/80 shadow-sm
              num-pop transition-all duration-300 hover:shadow-md hover:-translate-y-0.5"
              style={{ animationDelay: "0ms" }}>
              <span className="block text-[20px] font-black text-slate-900 tabular-nums leading-none">{userMsgCount}</span>
              <span className="text-[9px] text-slate-400 mt-1 block font-semibold">提问</span>
            </div>
            <div className="rounded-xl px-3 py-2.5 text-center
              bg-white border border-amber-200/40 shadow-sm
              num-pop transition-all duration-300 hover:shadow-md hover:-translate-y-0.5"
              style={{ animationDelay: "100ms" }}>
              <span className="block text-[20px] font-black text-gradient-amber tabular-nums leading-none">{recommendations.length}</span>
              <span className="text-[9px] text-slate-400 mt-1 block font-semibold">推荐</span>
            </div>
          </div>
        </div>

        {/* ── Thinking timeline ── */}
        {thinkingSteps.length > 0 && (
          <div className="px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-[0.18em]">协作过程</span>
              {total > 0 && (
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md
                  ${hasError ? "text-red-600 bg-red-50 border border-red-200/50" :
                    isStreaming ? "text-amber-600 bg-amber-50 border border-amber-200/50" :
                    "text-emerald-600 bg-emerald-50 border border-emerald-200/50"}`}>
                  {doneCount}/{total}
                </span>
              )}
            </div>

            {/* Progress bar */}
            {total > 0 && (
              <div className="h-[5px] bg-slate-100 rounded-full mb-3 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ease-out ${
                    hasError ? "bg-gradient-to-r from-red-400 to-red-500" :
                    isStreaming ? "thinking-bar progress-glow-animated" :
                    "bg-gradient-to-r from-emerald-400 to-emerald-500"
                  }`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            )}

            {/* Agent steps with timeline connectors */}
            <div className="space-y-0">
              {thinkingSteps.map((step, i) => (
                <AgentStatusCard
                  key={`${step.agentKey}-${i}`}
                  agentKey={step.agentKey}
                  status={step.status}
                  message={step.message}
                  duration={step.duration}
                  startTime={step.startTime}
                  justCompleted={step.justCompleted}
                  index={i}
                  isLast={i === thinkingSteps.length - 1}
                />
              ))}
            </div>
          </div>
        )}

        {/* ── Favorites ── */}
        {favoriteIds.size > 0 && (
          <div className="px-4 py-3 border-t border-slate-200/50">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-[0.18em]">收藏</span>
            <div className="mt-2 flex items-center gap-2.5
              px-3 py-2 rounded-xl bg-white
              border border-amber-200/40 shadow-sm
              transition-all duration-300 hover:shadow-md hover:-translate-y-0.5">
              <span className="text-lg">♥</span>
              <span className="text-lg font-black text-gradient-amber">{favoriteIds.size}</span>
              <span className="text-[11px] text-slate-400 font-semibold">家已收藏</span>
            </div>
          </div>
        )}

        {/* ── Empty state ── */}
        {!hasActivity && messages.length === 0 && (
          <div className="px-4 py-12 text-center">
            <div className="relative w-14 h-14 mx-auto mb-4">
              <div className="absolute inset-[-20%] rounded-full bg-slate-100/40 blur-xl animate-breathe" />
              <div className="relative w-14 h-14 rounded-2xl bg-white border border-slate-100/80 shadow-sm
                flex items-center justify-center
                transition-transform duration-300 hover:scale-110 hover:shadow-md">
                <AeroSavorIcon size={24} className="opacity-20" />
              </div>
            </div>
            <p className="text-[12px] text-slate-500 font-bold">智能体状态面板</p>
            <p className="text-[10px] text-slate-300 mt-1.5 leading-relaxed">
              发送消息后这里会显示<br/>智能体协作过程
            </p>

            {/* Agent type indicators */}
            <div className="mt-5 flex flex-wrap justify-center gap-1">
              {["💭", "📍", "📋", "🔍", "⭐", "💡"].map((icon, i) => (
                <span
                  key={i}
                  className="w-7 h-7 rounded-lg bg-white border border-slate-100/80 shadow-sm
                    flex items-center justify-center text-xs
                    hover:scale-110 hover:shadow-md transition-all duration-300 cursor-default"
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  {icon}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Footer: Connection health ── */}
      <div className="px-4 py-2.5 border-t border-slate-200/50 bg-transparent">
        <div className="flex items-center justify-center gap-1.5">
          {isStreaming && !sseHealthy ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" style={{ animationDuration: "1s" }} />
              <p className="text-[9px] text-amber-500 font-bold tracking-wider uppercase">重连中...</p>
            </>
          ) : isStreaming && sseHealthy ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/30 animate-pulse" style={{ animationDuration: "3s" }} />
              <p className="text-[9px] text-emerald-500 font-bold tracking-wider uppercase">已连接</p>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/30 animate-pulse" style={{ animationDuration: "3s" }} />
              <p className="text-[9px] text-slate-300 font-bold tracking-wider uppercase">AeroSavor</p>
            </>
          )}
        </div>
      </div>
    </aside>
  )
}

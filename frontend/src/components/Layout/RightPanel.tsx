import { useEffect, useState } from "react"
import { useChatStore, type ThinkingStepStatus } from "../../store/chat"
import { agentIcons, agentLabels } from "../../constants/agents"
import { AeroSavorIcon } from "../../assets/Logo"
import { useElapsedTime } from "../../hooks/useElapsedTime"

/** Status color mapping - minimal */
const statusDot: Record<ThinkingStepStatus, string> = {
  running: "bg-amber-400 animate-pulse",
  done: "bg-emerald-400",
  error: "bg-red-400",
  decision: "bg-indigo-400",
  collaboration: "bg-teal-400",
  delegation: "bg-blue-400",
  quality_retry: "bg-purple-400",
}

/** Compact agent row - single line, no timeline connector */
function AgentRow({ agentKey, status, message, duration, startTime }: {
  agentKey: string
  status: ThinkingStepStatus
  message: string
  duration?: number
  startTime?: number
}) {
  const isRunning = status === "running"
  const isDone = status === "done"
  const isError = status === "error"

  const elapsedText = useElapsedTime(startTime, isRunning)
  const durationText = duration != null && duration > 0
    ? duration < 1000 ? `${duration}ms` : `${(duration / 1000).toFixed(1)}s`
    : null

  return (
    <div className={`flex items-center gap-2.5 py-1.5 px-2.5 rounded-lg text-[11px]
      transition-opacity duration-300
      ${isRunning ? "bg-amber-50/80 border border-amber-200/40" : ""}
      ${isDone ? "opacity-40" : ""}
      ${isError ? "bg-red-50/60 border border-red-200/40" : ""}
      ${!isRunning && !isDone && !isError ? "bg-slate-50/50 border border-slate-100/40" : ""}
    `}>
      {/* Status dot */}
      <span className={`shrink-0 w-2 h-2 rounded-full ${statusDot[status]}`} />

      {/* Icon */}
      <span className="shrink-0 text-[12px]">{agentIcons[agentKey] ?? "⚙️"}</span>

      {/* Name + message */}
      <span className="flex-1 min-w-0 truncate font-semibold text-slate-700">
        {agentLabels[agentKey] || agentKey}
      </span>

      {/* Timer / duration */}
      {isRunning && elapsedText && (
        <span className="shrink-0 text-[9px] text-amber-500/70 font-mono font-bold bg-amber-100/50 px-1.5 py-0.5 rounded">
          {elapsedText}
        </span>
      )}
      {isDone && durationText && (
        <span className="shrink-0 text-[9px] text-emerald-500/60 font-mono bg-emerald-50 px-1.5 py-0.5 rounded">
          {durationText}
        </span>
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

  const userMsgCount = messages.filter((m) => m.role === "user").length

  const progressPct = total > 0 ? Math.round((doneCount / total) * 100) : 0

  // Current running agent
  const currentAgent = [...thinkingSteps].reverse().find((s) => s.status === "running")

  // SSE health
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
    <aside className="w-[260px] shrink-0 h-full flex flex-col bg-[#FAFAF8]/95 backdrop-blur-xl border-l border-slate-200/50">

      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-3 border-b border-slate-200/50">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 via-orange-400 to-orange-500
              flex items-center justify-center shadow-lg shadow-amber-500/25">
              <AeroSavorIcon size={15} />
            </div>
            {isStreaming && (
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
                animate-ping opacity-20" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-[13px] font-bold text-slate-900 block">协作状态</span>
            <span className={`text-[10px] font-semibold ${
              isStreaming ? "text-amber-600" : allDone ? "text-emerald-600" : "text-slate-400"
            }`}>
              {isStreaming
                ? currentAgent ? `${currentAgent.agent || "智能体"}思考中...` : "运行中..."
                : allDone ? "已完成" : hasActivity ? "处理中" : "待命"}
            </span>
          </div>

          {/* Connection indicator */}
          {isStreaming && (
            <span className={`w-2 h-2 rounded-full shrink-0 ${
              sseHealthy ? "bg-emerald-400 shadow-sm shadow-emerald-400/30" : "bg-amber-400 animate-pulse"
            }`} />
          )}
        </div>

        {/* Progress bar */}
        {total > 0 && (
          <div className="mt-3 h-[3px] bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                hasError ? "bg-gradient-to-r from-red-400 to-red-500" :
                isStreaming ? "thinking-bar" :
                "bg-gradient-to-r from-emerald-400 to-emerald-500"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        )}
      </div>

      {/* ── Scrollable content ── */}
      <div className="flex-1 overflow-y-auto">

        {/* ── Quick stats ── */}
        <div className="px-4 py-3 border-b border-slate-200/50">
          <div className="grid grid-cols-3 gap-1.5">
            <div className="rounded-lg px-2 py-2 text-center bg-white border border-slate-100/80 shadow-sm">
              <span className="block text-[16px] font-black text-slate-900 tabular-nums leading-none">{userMsgCount}</span>
              <span className="text-[8px] text-slate-400 mt-0.5 block font-bold">提问</span>
            </div>
            <div className="rounded-lg px-2 py-2 text-center bg-white border border-amber-200/30 shadow-sm">
              <span className="block text-[16px] font-black text-gradient-amber tabular-nums leading-none">{recommendations.length}</span>
              <span className="text-[8px] text-slate-400 mt-0.5 block font-bold">推荐</span>
            </div>
            <div className="rounded-lg px-2 py-2 text-center bg-white border border-slate-100/80 shadow-sm">
              <span className="block text-[16px] font-black text-slate-900 tabular-nums leading-none">{doneCount}/{total}</span>
              <span className="text-[8px] text-slate-400 mt-0.5 block font-bold">步骤</span>
            </div>
          </div>
        </div>

        {/* ── Agent steps - compact single-line ── */}
        {thinkingSteps.length > 0 && (
          <div className="px-3 py-3">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-[0.15em] px-1">协作过程</span>
            <div className="mt-2 space-y-1">
              {thinkingSteps.map((step, i) => (
                <AgentRow
                  key={`${step.agentKey}-${i}`}
                  agentKey={step.agentKey}
                  status={step.status}
                  message={step.message}
                  duration={step.duration}
                  startTime={step.startTime}
                />
              ))}
            </div>
          </div>
        )}

        {/* ── Favorites ── */}
        {favoriteIds.size > 0 && (
          <div className="px-4 py-3 border-t border-slate-200/50">
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white
              border border-amber-200/40 shadow-sm">
              <span className="text-base">♥</span>
              <span className="text-sm font-black text-gradient-amber">{favoriteIds.size}</span>
              <span className="text-[10px] text-slate-400 font-semibold">家已收藏</span>
            </div>
          </div>
        )}

        {/* ── Empty state ── */}
        {!hasActivity && messages.length === 0 && (
          <div className="px-4 py-16 text-center">
            <div className="relative w-12 h-12 mx-auto mb-4">
              <div className="absolute inset-[-20%] rounded-full bg-slate-100/40 blur-xl animate-breathe" />
              <div className="relative w-12 h-12 rounded-2xl bg-white border border-slate-100/80 shadow-sm
                flex items-center justify-center">
                <AeroSavorIcon size={20} className="opacity-20" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 font-bold">智能体状态</p>
            <p className="text-[10px] text-slate-300 mt-1.5 leading-relaxed">
              发送消息后<br/>这里会显示协作过程
            </p>
          </div>
        )}
      </div>

      {/* ── Footer ── */}
      <div className="px-4 py-2 border-t border-slate-200/50">
        <div className="flex items-center justify-center gap-1.5">
          {isStreaming && !sseHealthy ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" style={{ animationDuration: "1s" }} />
              <p className="text-[9px] text-amber-500 font-bold">重连中...</p>
            </>
          ) : isStreaming ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/30 animate-pulse" style={{ animationDuration: "3s" }} />
              <p className="text-[9px] text-emerald-500 font-bold">已连接</p>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
              <p className="text-[9px] text-slate-300 font-bold">AeroSavor</p>
            </>
          )}
        </div>
      </div>
    </aside>
  )
}

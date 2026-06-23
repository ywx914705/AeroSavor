import { useState } from "react"
import { useChatStore, type ThinkingStepStatus } from "../../store/chat"
import { agentIcons, agentLabels } from "../../constants/agents"
import { useElapsedTime } from "../../hooks/useElapsedTime"

/** Status color mapping */
const statusColors: Record<ThinkingStepStatus, { bg: string; border: string; text: string; dot: string; glow: string }> = {
  running:       { bg: "bg-amber-50", border: "border-amber-300/50", text: "text-amber-700", dot: "bg-amber-400", glow: "shadow-amber-200/60" },
  done:          { bg: "bg-emerald-50/50", border: "border-emerald-200/30", text: "text-emerald-600", dot: "bg-emerald-400", glow: "" },
  error:         { bg: "bg-red-50", border: "border-red-300/50", text: "text-red-600", dot: "bg-red-400", glow: "shadow-red-200/60" },
  decision:      { bg: "bg-indigo-50", border: "border-indigo-300/40", text: "text-indigo-600", dot: "bg-indigo-400", glow: "shadow-indigo-200/40" },
  collaboration: { bg: "bg-teal-50", border: "border-teal-300/40", text: "text-teal-600", dot: "bg-teal-400", glow: "shadow-teal-200/40" },
  delegation:    { bg: "bg-blue-50", border: "border-blue-300/40", text: "text-blue-600", dot: "bg-blue-400", glow: "shadow-blue-200/40" },
  quality_retry: { bg: "bg-purple-50", border: "border-purple-300/40", text: "text-purple-600", dot: "bg-purple-400", glow: "shadow-purple-200/40" },
}

/** Status icon mapping */
const statusIcons: Record<ThinkingStepStatus, string> = {
  running: "⚡",
  done: "✓",
  error: "✕",
  decision: "💡",
  collaboration: "🔗",
  delegation: "🤝",
  quality_retry: "🔄",
}

/** Single agent step row with rich visual feedback */
function AgentStepRow({ step, index, isLast, isExpanded }: {
  step: ReturnType<typeof useChatStore.getState>["thinkingSteps"][0]
  index: number
  isLast: boolean
  isExpanded: boolean
}) {
  const isRunning = step.status === "running"
  const isDone = step.status === "done"
  const isError = step.status === "error"
  const colors = statusColors[step.status]

  // Live elapsed timer for running agents
  const elapsedText = useElapsedTime(step.startTime, isRunning)

  // Duration display for done agents
  const durationText = step.duration != null && step.duration > 0
    ? step.duration < 1000 ? `${step.duration}ms` : `${(step.duration / 1000).toFixed(1)}s`
    : null

  // Completion flash state
  const [flashActive, setFlashActive] = useState(false)
  if (step.justCompleted && !flashActive) {
    setFlashActive(true)
    setTimeout(() => setFlashActive(false), 800)
  }

  return (
    <div className="relative">
      {/* Step card */}
      <div
        className={`relative flex items-center gap-3 py-2.5 px-3 rounded-xl
          transition-all duration-400 group
          ${isRunning ? `${colors.bg} ${colors.border} border shadow-sm ${colors.glow}` : ""}
          ${isDone && !isRunning ? "opacity-60 hover:opacity-90" : ""}
          ${isError ? `${colors.bg} ${colors.border} border shadow-sm` : ""}
          ${!isRunning && !isDone && !isError ? `${colors.bg} ${colors.border} border shadow-sm` : ""}
          ${flashActive ? "animate-completion-flash" : ""}`}
        style={{
          animation: flashActive ? undefined : `slide-in-left 0.4s cubic-bezier(0.22,1,0.36,1) ${index * 80}ms both`,
        }}
      >
        {/* Icon badge */}
        <div className={`relative z-10 shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-[13px]
          ${isRunning
            ? "bg-white border-2 border-amber-300 shadow-md shadow-amber-200/50 animate-glow-pulse"
            : isDone
            ? "bg-gradient-to-br from-emerald-50 to-emerald-100 border-2 border-emerald-300 shadow-sm"
            : isError
            ? "bg-white border-2 border-red-300 shadow-sm"
            : "bg-white border-2 " + colors.border + " shadow-sm"
          }`}>
          {isRunning ? (
            <span className="animate-pulse">{agentIcons[step.agentKey] ?? "⚙️"}</span>
          ) : isDone ? (
            <svg width="12" height="12" viewBox="0 0 8 8" fill="none" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round">
              <path d="M1.5 4l2 2 3-3.5" />
            </svg>
          ) : isError ? (
            <span className="text-red-500 text-[11px] font-bold">✕</span>
          ) : (
            <span>{agentIcons[step.agentKey] ?? statusIcons[step.status]}</span>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-[12px] font-bold leading-tight truncate ${colors.text}`}>
              {step.agent}
            </span>
            {isRunning && (
              <span className="flex gap-[2px] ml-0.5">
                <span className="typing-dot-premium" style={{ animationDelay: "0ms" }} />
                <span className="typing-dot-premium" style={{ animationDelay: "0.16s" }} />
                <span className="typing-dot-premium" style={{ animationDelay: "0.32s" }} />
              </span>
            )}
            {/* Live timer */}
            {isRunning && elapsedText && (
              <span className="text-[10px] text-amber-500/80 font-mono font-semibold bg-amber-100/60 px-1.5 py-0.5 rounded-md">
                {elapsedText}
              </span>
            )}
            {/* Duration badge for done */}
            {durationText && isDone && (
              <span className="text-[10px] text-emerald-500/70 font-mono bg-emerald-50 px-1.5 py-0.5 rounded-md">
                {durationText}
              </span>
            )}
          </div>
          {/* Message line */}
          {isExpanded && step.message && (
            <p className={`text-[10px] leading-tight mt-0.5 truncate
              ${isRunning ? "text-amber-600/70" : isDone ? "text-slate-400" : isError ? "text-red-500/70" : colors.text + "/70"}`}>
              {step.message}
            </p>
          )}
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

      {/* Timeline connector */}
      {!isLast && (
        <div className="timeline-connector">
          {isDone && <div className="timeline-connector-fill-done" />}
          {isRunning && <div className="timeline-connector-fill-running" />}
          {isError && <div className="timeline-connector-fill-error" />}
        </div>
      )}
    </div>
  )
}

/** Main ThinkingPanel — full-featured agent collaboration status */
export function ThinkingPanel() {
  const { thinkingSteps, thinkingVisible, isStreaming, hasError } = useChatStore()
  const [expanded, setExpanded] = useState(true) // Default expanded for better visibility

  if (!thinkingVisible || thinkingSteps.length === 0) return null

  const runningCount = thinkingSteps.filter((s) => s.status === "running").length
  const doneCount = thinkingSteps.filter((s) => s.status === "done").length
  const errorCount = thinkingSteps.filter((s) => s.status === "error").length
  const total = thinkingSteps.length
  const progressPct = total > 0 ? Math.round((doneCount / total) * 100) : 0
  const lastRunning = [...thinkingSteps].reverse().find((s) => s.status === "running")

  return (
    <div className="mb-6">
      {/* 主卡片：使用 opacity + translate 做进出动画，不改变占位高度 */}
      <div className={`relative overflow-hidden rounded-2xl transition-opacity duration-500 ${
        !thinkingVisible || thinkingSteps.length === 0
          ? "opacity-0 max-h-0 pointer-events-none"
          : "opacity-100 animate-reveal-blur"
      } ${
        hasError
          ? "bg-white border-2 border-red-200/60 shadow-lg shadow-red-100/30"
          : runningCount > 0
          ? "bg-white border-2 border-amber-200/50 shadow-lg shadow-amber-100/30"
          : "bg-white border border-emerald-200/40 shadow-md shadow-emerald-100/20"
      }`}>

        {/* Animated gradient top bar */}
        <div className={`h-1 w-full ${
          hasError ? "bg-gradient-to-r from-red-400 via-red-500 to-red-400" :
          runningCount > 0 ? "thinking-bar" :
          "bg-gradient-to-r from-emerald-400 via-emerald-500 to-emerald-400"
        }`} />

        {/* Header row */}
        <div
          className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none hover:bg-slate-50/50 transition-colors"
          onClick={() => setExpanded(!expanded)}
        >
          {/* Animated spinner */}
          {runningCount > 0 ? (
            <div className="relative w-5 h-5 shrink-0">
              <span className="absolute inset-0 w-5 h-5 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
              <span className="absolute inset-0 w-5 h-5 border-2 border-transparent border-b-orange-300 rounded-full animate-spin"
                style={{ animationDirection: "reverse", animationDuration: "0.8s" }} />
            </div>
          ) : errorCount > 0 ? (
            <span className="w-5 h-5 rounded-full bg-gradient-to-br from-red-400 to-red-500 shadow-sm shadow-red-500/20
              flex items-center justify-center text-[9px] text-white font-bold shrink-0">!</span>
          ) : (
            <span className="w-5 h-5 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-500 shadow-sm shadow-emerald-500/20 shrink-0
              flex items-center justify-center">
              <svg width="10" height="10" viewBox="0 0 8 8" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                <path d="M1.5 4l2 2 3-3.5" />
              </svg>
            </span>
          )}

          {/* Status text */}
          <div className="flex-1 min-w-0">
            <span className={`text-[13px] font-bold ${errorCount > 0 ? "text-red-600" : runningCount > 0 ? "text-amber-700" : "text-emerald-600"}`}>
              {runningCount > 0
                ? `${lastRunning?.agent || "智能体"} 正在思考...`
                : errorCount > 0
                ? `${errorCount} 个任务出错`
                : "全部完成"
              }
            </span>
          </div>

          {/* Progress badge */}
          <span className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-lg
            ${hasError ? "text-red-600 bg-red-50 border border-red-200/50" :
              runningCount > 0 ? "text-amber-600 bg-amber-50 border border-amber-200/50" :
              "text-emerald-600 bg-emerald-50 border border-emerald-200/50"}`}>
            {doneCount}/{total}
          </span>

          {/* Expand/collapse chevron */}
          <svg
            width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
            className={`text-slate-300 transition-transform duration-300 shrink-0 ${expanded ? "rotate-180" : ""}`}
          >
            <path d="M3 5l3 3 3-3" />
          </svg>
        </div>

        {/* Progress bar */}
        {total > 0 && (
          <div className="mx-4 h-[4px] bg-slate-100 rounded-full overflow-hidden mb-1">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                hasError ? "bg-gradient-to-r from-red-400 to-red-500" :
                runningCount > 0 ? "thinking-bar" :
                "bg-gradient-to-r from-emerald-400 to-emerald-500"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        )}

        {/* Expandable agent steps */}
        {expanded && (
          <div className="thinking-panel-expand px-3 py-2 max-h-[250px] md:max-h-[400px] overflow-y-auto">
            {thinkingSteps.map((step, i) => (
              <AgentStepRow
                key={`${step.agentKey}-${i}`}
                step={step}
                index={i}
                isLast={i === thinkingSteps.length - 1}
                isExpanded={expanded}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

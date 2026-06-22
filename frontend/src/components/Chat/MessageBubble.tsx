import ReactMarkdown from "react-markdown"
import type { ChatMessage } from "../../store/chat"
import { useChatStore } from "../../store/chat"
import { AeroSavorIcon } from "../../assets/Logo"
import { useTypewriter } from "../../hooks/useTypewriter"

function formatTime(ts?: number): string {
  if (!ts) return ""
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

function getLoadingText(steps: { agentKey: string; status: string }[]): string {
  const running = steps.filter((s) => s.status === "running")
  const keys = running.map((s) => s.agentKey)
  if (keys.some((k) => k === "search_agent" || k === "recommend_agent"))
    return "正在为您寻找最佳推荐"
  if (keys.some((k) => k === "route_agent"))
    return "正在规划路线"
  if (keys.length > 0) return "正在思考..."
  return "正在回复..."
}

/** Agent content with typewriter and streaming glow */
function AgentContent({ content }: { content: string }) {
  const isStreaming = useChatStore((s) => s.isStreaming)
  const displayed = useTypewriter(content)
  const showCursor = isStreaming && displayed.length < content.length

  return (
    <div className="prose-ed">
      <ReactMarkdown>{displayed}</ReactMarkdown>
      {showCursor && (
        <span className="glow-typing-cursor" />
      )}
    </div>
  )
}

/** Animated thinking dots */
function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="typing-dot-premium"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  )
}

/** Loading state with spinner */
function LoadingState({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-4 py-2">
      <div className="relative">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
          flex items-center justify-center shadow-lg shadow-amber-500/25
          animate-pulse">
          <AeroSavorIcon size={18} />
        </div>
        <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
          animate-ping opacity-20" />
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-slate-700">{text}</span>
        <ThinkingDots />
      </div>
    </div>
  )
}

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user"
  const isStreaming = useChatStore((s) => s.isStreaming)
  const thinkingSteps = useChatStore((s) => s.thinkingSteps)
  const recommendations = useChatStore((s) => s.recommendations)
  const loadingText = getLoadingText(thinkingSteps)
  const stamp = formatTime(msg.timestamp)

  const showLoading = !isUser && !msg.content && !(recommendations.length > 0)
  const isAgentStreaming = !isUser && isStreaming && msg.content

  return (
    <div className={`mb-8 clear-both ${isUser ? "msg-glide-right text-right" : "msg-glide-left text-left"}`}>
      {/* Avatar + Name row */}
      <div className={`flex items-center gap-3 mb-2.5 ${isUser ? "justify-end" : "justify-start"}`}>
        {!isUser && (
          <div className="relative">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 via-orange-400 to-orange-500
              flex items-center justify-center shadow-md shadow-amber-500/25 shrink-0
              transition-transform duration-300 hover:scale-110">
              <AeroSavorIcon size={16} />
            </div>
            {isAgentStreaming && (
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
                animate-ping opacity-15" />
            )}
          </div>
        )}
        <span className={`text-[11px] font-bold ${isUser ? "text-slate-400" : "text-gradient-amber"}`}>
          {isUser ? "你" : "AeroSavor"}
        </span>
        {stamp && (
          <span className="text-[10px] text-slate-300 font-mono font-medium">{stamp}</span>
        )}
        {isUser && (
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-slate-700 via-slate-800 to-slate-900
            flex items-center justify-center shrink-0 shadow-md shadow-slate-900/15
            transition-transform duration-300 hover:scale-110">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
              strokeWidth="1.5" strokeLinecap="round" className="text-slate-300">
              <circle cx="7" cy="5" r="2.5" />
              <path d="M2.5 12c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" />
            </svg>
          </div>
        )}
      </div>

      {/* Bubble */}
      <div
        className={`inline-block text-left max-w-[88%] md:max-w-[78%] transition-all duration-500 ${
          isUser
            ? "bg-gradient-to-br from-slate-800 via-slate-800 to-slate-900 text-white rounded-[20px] rounded-tr-md px-5 py-3.5 shadow-xl shadow-slate-900/10"
            : `bg-white rounded-[20px] rounded-tl-md px-5 py-3.5 border border-slate-100/70 shadow-md shadow-slate-100/40
              ${isAgentStreaming ? "streaming-border-active" : "hover:shadow-lg hover:shadow-slate-200/50"}`
        }`}
      >
        {isUser ? (
          <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
        ) : msg.content ? (
          <AgentContent content={msg.content} />
        ) : showLoading ? (
          <LoadingState text={loadingText} />
        ) : (
          <div className="flex items-center gap-3 py-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
            </span>
            <span className="text-[13px] text-slate-500 font-medium">生成回复中...</span>
          </div>
        )}
      </div>
    </div>
  )
}

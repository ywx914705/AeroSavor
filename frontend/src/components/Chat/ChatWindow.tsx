import { Component, type ReactNode, useCallback, useEffect, useRef, useState } from "react"
import { useChat } from "../../hooks/useChat"
import { useChatStore } from "../../store/chat"
import { MessageBubble } from "./MessageBubble"
import { InputBar } from "./InputBar"
import { ThinkingPanel } from "./ThinkingPanel"
import { CardStack } from "../Restaurant/CardStack"
import { RoutePanel } from "../Restaurant/RoutePanel"
import { MapView } from "../Map/MapView"
import { LeftSidebar } from "../Layout/LeftSidebar"
import { RightPanel } from "../Layout/RightPanel"
import { HeroSection } from "../Layout/HeroSection"
import { BackgroundEffects } from "../Effects/BackgroundEffects"
import { LocationPromptModal } from "./LocationPromptModal"
import { AeroSavorIcon } from "../../assets/Logo"

// ── Error Boundary ──

interface EBState { hasError: boolean; error: Error | null }

class ErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  state: EBState = { hasError: false, error: null }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen p-10 text-center bg-[#FAFAF8]">
          <div className="relative mb-8">
            <div className="absolute inset-0 w-32 h-32 -m-8 rounded-3xl bg-red-100/40 blur-3xl" />
            <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-red-50 to-red-100 border border-red-200/60
              flex items-center justify-center shadow-lg shadow-red-100/50">
              <AeroSavorIcon size={40} className="opacity-30" />
            </div>
          </div>
          <h2 className="text-2xl font-black text-slate-900 mb-3">出了点问题</h2>
          <p className="text-sm text-slate-500 mb-8 max-w-md leading-relaxed font-medium">
            {this.state.error?.message || "发生了未知错误"}
          </p>
          <button onClick={() => window.location.reload()}
            className="px-8 py-3.5 bg-gradient-to-r from-amber-500 via-amber-400 to-orange-500 text-white text-sm font-bold rounded-2xl
              hover:from-amber-600 hover:via-amber-500 hover:to-orange-600 transition-all duration-400
              shadow-xl shadow-amber-500/25 hover:shadow-2xl hover:shadow-amber-500/35 hover:-translate-y-0.5
              active:scale-95 focus:outline-none focus:ring-2 focus:ring-amber-300/50 focus:ring-offset-2">
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ── Center top bar ──

function CenterTopBar() {
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen)
  const userLocation = useChatStore((s) => s.userLocation)
  const setLocationPromptPending = useChatStore((s) => s.setLocationPromptPending)
  const now = new Date()
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][now.getDay()]
  const dateStr = `${now.getMonth() + 1}.${now.getDate()}`

  return (
    <div className="h-14 shrink-0 flex items-center justify-between px-5 border-b border-slate-200/50 glass-strong">
      {/* Mobile menu */}
      <button
        onClick={() => setSidebarOpen(true)}
        className="md:hidden w-9 h-9 rounded-xl flex items-center justify-center
          text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-all duration-300
          focus:outline-none focus:ring-2 focus:ring-amber-300/50"
        aria-label="历史记录"
      >
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M3 4h10M3 8h10M3 12h10" />
        </svg>
      </button>

      <div className="flex items-center gap-4 text-xs text-slate-400 font-semibold">
        {userLocation ? (
          <span className="flex items-center gap-2 text-emerald-500 font-bold text-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            已定位
          </span>
        ) : (
          <button
            onClick={() => setLocationPromptPending("")}
            className="flex items-center gap-2 text-slate-400 font-bold text-xs
              hover:text-amber-500 transition-colors cursor-pointer group"
          >
            <span className="w-2 h-2 rounded-full bg-slate-300 group-hover:bg-amber-400 transition-colors" />
            点击定位
          </button>
        )}
        <span className="text-slate-200">|</span>
        <span>{weekday}</span>
        <span className="font-mono text-slate-300 font-bold">{dateStr}</span>
      </div>

      <div className="w-9 md:w-0" />
    </div>
  )
}

// ── Scroll to bottom ──

function ScrollToBottom({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="absolute bottom-4 right-4 z-10 w-10 h-10 rounded-xl
        bg-white border border-slate-200 shadow-xl shadow-slate-200/50
        flex items-center justify-center text-slate-500
        hover:text-amber-500 hover:border-amber-200 hover:shadow-amber-100/50
        transition-all duration-400 active:scale-95 hover:-translate-y-0.5
        focus:outline-none focus:ring-2 focus:ring-amber-300/50"
      aria-label="滚动到底部"
    >
      <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M6 2v8M2.5 6.5L6 10l3.5-3.5" />
      </svg>
    </button>
  )
}

// ── Main Content ──

function ChatContent() {
  const {
    sessionId,
    messages,
    recommendations,
    isStreaming,
    favoriteIds,
    routeInfo,
    toggleFavorite,
    reset,
  } = useChatStore()
  const { sendMessage, stopGeneration, sendFeedback } = useChat()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const userScrolledUp = useRef(false)

  const lastMsgLen = messages.length > 0 ? messages[messages.length - 1].content.length : 0

  const scrollToBottom = useCallback(() => {
    userScrolledUp.current = false
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [])

  // Auto-scroll only when user is near the bottom
  useEffect(() => {
    const el = scrollRef.current
    if (!el || userScrolledUp.current) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (isNearBottom) {
      requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight })
      })
    }
  }, [messages.length, lastMsgLen, recommendations.length])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      setShowScrollBtn(distFromBottom > 120)
      // If user scrolls up during streaming, don't force them back
      if (distFromBottom > 300) {
        userScrolledUp.current = true
      } else if (distFromBottom < 50) {
        userScrolledUp.current = false
      }
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [])

  const hasContent = messages.length > 0 || recommendations.length > 0

  return (
    <div className="flex h-screen bg-[#FAFAF8] overflow-hidden">
      {/* Background effects: grid pattern + grain texture */}
      <BackgroundEffects />

      {/* Left: History sidebar */}
      <LeftSidebar />

      {/* Center: Chat area */}
      <div className="flex-1 flex flex-col min-w-0 bg-transparent">
        <CenterTopBar />

        <div ref={scrollRef} className="flex-1 overflow-y-auto relative" role="log">
          {hasContent ? (
            <div className="px-5 md:px-8 py-5 md:py-8">
              <div className="max-w-2xl mx-auto">
                {messages.map((m) => (
                  <MessageBubble key={m.id} msg={m} />
                ))}

                {/* Agent thinking process - inline in chat */}
                <ThinkingPanel />

                {recommendations.length > 0 && (
                  <div className="mt-8 mb-6 animate-reveal-blur">
                    <MapView
                      restaurants={recommendations.slice(0, 5)}
                      center={recommendations[0]?.location}
                    />
                  </div>
                )}

                {routeInfo && (
                  <div className="animate-reveal-blur">
                    <RoutePanel route={routeInfo} destinationName={routeInfo.destination_name} />
                  </div>
                )}

                {recommendations.length > 0 && (
                  <CardStack
                    restaurants={recommendations}
                    sessionId={sessionId}
                    onFeedback={sendFeedback}
                    onToggleFavorite={toggleFavorite}
                    favoriteIds={favoriteIds}
                  />
                )}
              </div>
            </div>
          ) : (
            <HeroSection onSend={sendMessage} />
          )}

          {showScrollBtn && <ScrollToBottom onClick={scrollToBottom} />}
        </div>

        <InputBar onSend={sendMessage} onStop={stopGeneration} disabled={isStreaming} />
      </div>

      {/* Right: Agent status panel */}
      <div className="hidden md:block">
        <RightPanel />
      </div>

      {/* 按需定位弹窗 */}
      <LocationPromptModal />
    </div>
  )
}

export function ChatWindow() {
  return (
    <ErrorBoundary>
      <ChatContent />
    </ErrorBoundary>
  )
}

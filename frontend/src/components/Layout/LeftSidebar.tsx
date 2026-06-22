import { useState, useEffect, useRef } from "react"
import { getHistory, getSessionMessages, deleteSession, renameSession } from "../../api/client"
import { useChatStore } from "../../store/chat"
import { AeroSavorIcon } from "../../assets/Logo"

interface SessionItem {
  id: string
  created_at: string
  last_message: string
  title: string | null
  turn_count: number
}

function formatStamp(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    if (d.toDateString() === now.toDateString()) {
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
    }
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (d.toDateString() === yesterday.toDateString()) return "昨天"
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return ""
  }
}

function groupByDate(sessions: SessionItem[]) {
  const groups: { label: string; items: SessionItem[] }[] = []
  const now = new Date()
  const today: SessionItem[] = []
  const yesterday: SessionItem[] = []
  const older: SessionItem[] = []
  const yesterdayDate = new Date(now)
  yesterdayDate.setDate(yesterdayDate.getDate() - 1)

  sessions.forEach((s) => {
    try {
      const d = new Date(s.created_at)
      if (d.toDateString() === now.toDateString()) today.push(s)
      else if (d.toDateString() === yesterdayDate.toDateString()) yesterday.push(s)
      else older.push(s)
    } catch {
      older.push(s)
    }
  })

  if (today.length) groups.push({ label: "今天", items: today })
  if (yesterday.length) groups.push({ label: "昨天", items: yesterday })
  if (older.length) groups.push({ label: "更早", items: older })
  return groups
}

export function LeftSidebar() {
  const {
    sidebarOpen, setSidebarOpen,
    setSessionId, setMessages, setRecommendations, setRouteInfo,
    reset, sessionId: activeSessionId,
  } = useChatStore()
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingSession, setLoadingSession] = useState<string | null>(null)

  // Context menu state
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [menuPos, setMenuPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })

  // Inline rename state
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const renameRef = useRef<HTMLInputElement>(null)

  // Delete confirm state
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const refreshSessions = () => {
    setLoading(true)
    getHistory(50)
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    refreshSessions()
  }, [activeSessionId])

  // Focus rename input when it appears
  useEffect(() => {
    if (renamingId && renameRef.current) {
      renameRef.current.focus()
      renameRef.current.select()
    }
  }, [renamingId])

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return
    const close = () => setMenuOpen(null)
    window.addEventListener("click", close)
    return () => window.removeEventListener("click", close)
  }, [menuOpen])

  async function handleSessionClick(sessionId: string) {
    if (sessionId === activeSessionId || renamingId) return
    setLoadingSession(sessionId)
    try {
      const data = await getSessionMessages(sessionId)
      const msgs = (data.messages || []).map((m: any, i: number) => ({
        id: `hist-${sessionId}-${i}`,
        role: m.role as "user" | "assistant",
        content: m.content,
        timestamp: m.ts ? new Date(m.ts).getTime() : undefined,
      }))
      setSessionId(sessionId)
      setMessages(msgs)
      setRecommendations([])
      setRouteInfo(null)
      setSidebarOpen(false)
    } catch (e) {
      console.warn("load session failed", e)
    } finally {
      setLoadingSession(null)
    }
  }

  function handleContextMenu(e: React.MouseEvent, sessionId: string) {
    e.preventDefault()
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setMenuPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
    setMenuOpen(sessionId)
  }

  function handleMenuAction(action: "rename" | "delete", session: SessionItem) {
    setMenuOpen(null)
    if (action === "rename") {
      setRenamingId(session.id)
      setRenameValue(session.title || session.last_message || "")
    } else if (action === "delete") {
      setDeletingId(session.id)
    }
  }

  async function confirmRename() {
    if (!renamingId || !renameValue.trim()) {
      setRenamingId(null)
      return
    }
    try {
      await renameSession(renamingId, renameValue.trim())
      setSessions((prev) =>
        prev.map((s) => (s.id === renamingId ? { ...s, title: renameValue.trim() } : s))
      )
    } catch (e) {
      console.warn("rename failed", e)
    }
    setRenamingId(null)
  }

  async function confirmDelete() {
    if (!deletingId) return
    try {
      await deleteSession(deletingId)
      setSessions((prev) => prev.filter((s) => s.id !== deletingId))
      if (deletingId === activeSessionId) {
        reset()
      }
    } catch (e) {
      console.warn("delete failed", e)
    }
    setDeletingId(null)
  }

  const groups = groupByDate(sessions)

  return (
    <>
      {/* Mobile backdrop with blur */}
      <div
        className={`fixed inset-0 z-30 bg-black/30 backdrop-blur-sm md:hidden
          transition-all duration-500 ease-out
          ${sidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        onClick={() => setSidebarOpen(false)}
      />

      <aside className={`
        fixed md:relative z-40 md:z-auto top-0 left-0 h-full
        w-[280px] shrink-0 bg-[#FAFAF8] text-slate-800
        flex flex-col border-r border-slate-200/60
        transform transition-all duration-500 ease-out
        ${sidebarOpen ? "translate-x-0 shadow-2xl shadow-black/10" : "-translate-x-full md:translate-x-0"}
      `}>
        {/* Brand + close (mobile) */}
        <div className="px-5 pt-5 pb-3 flex items-center justify-between border-b border-slate-200/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500
              flex items-center justify-center shadow-lg shadow-amber-500/25
              transition-transform duration-300 hover:scale-110 hover:shadow-xl hover:shadow-amber-500/40">
              <AeroSavorIcon size={20} />
            </div>
            <span className="text-sm font-bold tracking-tight">
              <span className="text-amber-600">Aero</span>
              <span className="text-slate-800">Savor</span>
            </span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="md:hidden w-8 h-8 rounded-lg flex items-center justify-center
              text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all duration-300
              focus:outline-none focus:ring-2 focus:ring-amber-300/50"
            aria-label="关闭"
          >
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {/* New chat button */}
        <div className="px-4 pb-4 pt-3">
          <button
            onClick={() => { reset(); setSidebarOpen(false) }}
            className="w-full flex items-center justify-center gap-2.5 px-4 py-3 rounded-xl
              bg-white hover:bg-slate-50
              border border-slate-200/60 hover:border-slate-300/60
              text-sm text-slate-700 hover:text-slate-900 font-semibold
              transition-all duration-400 active:scale-[0.97] group
              shadow-sm hover:shadow-md
              focus:outline-none focus:ring-2 focus:ring-amber-300/50 focus:ring-offset-2 focus:ring-offset-[#FAFAF8]"
          >
            <svg width="15" height="15" viewBox="0 0 14 14" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round"
              className="text-amber-500 group-hover:rotate-90 transition-transform duration-400">
              <path d="M7 2v10M2 7h10" />
            </svg>
            新对话
          </button>
        </div>

        {/* Sessions */}
        <div className="flex-1 overflow-y-auto py-2 px-3 scrollbar-thin">
          {loading && (
            <div className="px-4 py-10 text-center">
              <div className="inline-flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-2 h-2 bg-amber-400/40 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
            </div>
          )}

          {!loading && sessions.length === 0 && (
            <div className="px-4 py-12 text-center">
              <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-slate-100 flex items-center justify-center border border-slate-200/60">
                <AeroSavorIcon size={24} className="opacity-25" />
              </div>
              <p className="text-xs text-slate-400 font-medium">暂无对话</p>
              <p className="text-[10px] text-slate-300 mt-1.5">开始新对话来寻找美食</p>
            </div>
          )}

          {groups.map((group, gi) => (
            <div key={group.label} className="mb-3"
              style={{ animation: `fade-up 0.4s ease-out ${gi * 100}ms both` }}>
              <div className="px-3 pt-4 pb-2">
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-[0.15em]">
                  {group.label}
                </span>
              </div>
              {group.items.map((s, si) => {
                const isActive = s.id === activeSessionId
                const isLoading = loadingSession === s.id
                const isRenaming = renamingId === s.id
                const displayName = s.title || s.last_message || "未命名会话"

                return (
                  <div key={s.id} className="relative mb-0.5"
                    style={{ animation: `slide-in-left 0.3s ease-out ${gi * 100 + si * 40}ms both` }}>
                    <button
                      onClick={() => handleSessionClick(s.id)}
                      onContextMenu={(e) => handleContextMenu(e, s.id)}
                      disabled={!!loadingSession || isRenaming}
                      className={`w-full text-left px-4 py-3 rounded-xl
                        transition-all duration-300 group relative
                        disabled:opacity-40
                        ${isActive
                          ? "bg-white text-slate-900 shadow-sm border border-slate-200/60"
                          : "text-slate-500 hover:bg-slate-50 hover:text-slate-700 hover:shadow-sm"
                        }`}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-8
                          bg-gradient-to-b from-amber-400 to-orange-500 rounded-r-full
                          shadow-lg shadow-amber-500/30" />
                      )}

                      {isRenaming ? (
                        <div className="pl-2 pr-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            ref={renameRef}
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") confirmRename()
                              if (e.key === "Escape") setRenamingId(null)
                            }}
                            onBlur={confirmRename}
                            maxLength={100}
                            className="w-full bg-white text-slate-800 text-sm px-3 py-2 rounded-lg
                              border border-amber-300/60 outline-none
                              focus:ring-2 focus:ring-amber-300/50 transition-all duration-200"
                          />
                        </div>
                      ) : (
                        <div className="flex items-center gap-3 min-w-0 pl-2 pr-8">
                          {isLoading && (
                            <span className="relative flex h-2 w-2 shrink-0">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                            </span>
                          )}
                          <span className="text-sm truncate flex-1 min-w-0 leading-snug font-medium">
                            {displayName}
                          </span>
                          <span className="text-[11px] text-slate-300 shrink-0 font-mono tabular">
                            {formatStamp(s.created_at)}
                          </span>
                        </div>
                      )}

                      {/* Hover: "..." button */}
                      {!isRenaming && (
                        <span
                          onClick={(e) => {
                            e.stopPropagation()
                            handleContextMenu(e, s.id)
                          }}
                          className="absolute right-2 top-1/2 -translate-y-1/2
                            w-7 h-7 rounded-lg flex items-center justify-center
                            opacity-0 group-hover:opacity-100
                            text-slate-300 hover:text-slate-500 hover:bg-slate-100
                            transition-all duration-200"
                          aria-label="更多操作"
                        >
                          <svg width="15" height="15" viewBox="0 0 14 14" fill="currentColor">
                            <circle cx="3" cy="7" r="1.2" />
                            <circle cx="7" cy="7" r="1.2" />
                            <circle cx="11" cy="7" r="1.2" />
                          </svg>
                        </span>
                      )}
                    </button>

                    {/* Context menu dropdown */}
                    {menuOpen === s.id && (
                      <div
                        className="absolute right-3 top-full z-50 mt-1
                          bg-white border border-slate-200/80 rounded-xl shadow-xl shadow-black/10
                          py-1.5 min-w-[130px] animate-menu-enter
                          backdrop-blur-xl"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => handleMenuAction("rename", s)}
                          className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs text-slate-600
                            hover:text-slate-900 hover:bg-slate-50 transition-all duration-200 rounded-lg mx-1"
                        >
                          <svg width="13" height="13" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                            <path d="M8.5 1.5l2 2M1 9l5.5-5.5 2 2L3 11H1V9z" />
                          </svg>
                          重命名
                        </button>
                        <div className="mx-3 my-1 border-t border-slate-100" />
                        <button
                          onClick={() => handleMenuAction("delete", s)}
                          className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs text-red-400
                            hover:text-red-600 hover:bg-red-50/60 transition-all duration-200 rounded-lg mx-1"
                        >
                          <svg width="13" height="13" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                            <path d="M2 3h8M4.5 3V2h3v1M3 3v7a1 1 0 001 1h4a1 1 0 001-1V3" />
                          </svg>
                          删除
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-200/50">
          <p className="text-[11px] text-slate-300 text-center font-medium">{sessions.length} 条对话</p>
        </div>
      </aside>

      {/* Delete confirmation modal */}
      {deletingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm
          animate-fade-in"
          onClick={() => setDeletingId(null)}>
          <div className="bg-white border border-slate-200/80 rounded-2xl p-7 w-[320px]
            shadow-2xl shadow-black/10 animate-pop-in"
            onClick={(e) => e.stopPropagation()}>
            <div className="w-12 h-12 mx-auto mb-4 rounded-2xl bg-red-50 flex items-center justify-center border border-red-200/60">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#EF4444" strokeWidth="2" strokeLinecap="round">
                <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
              </svg>
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-2 text-center">删除对话</h3>
            <p className="text-xs text-slate-500 mb-6 text-center leading-relaxed">删除后无法恢复，确定要继续吗？</p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeletingId(null)}
                className="px-5 py-2.5 text-xs text-slate-500 hover:text-slate-700 font-semibold
                  rounded-xl hover:bg-slate-50 transition-all duration-300
                  focus:outline-none focus:ring-2 focus:ring-slate-200"
              >
                取消
              </button>
              <button
                onClick={confirmDelete}
                className="px-5 py-2.5 text-xs text-white bg-gradient-to-r from-red-500 to-red-600
                  hover:from-red-600 hover:to-red-700
                  rounded-xl font-bold transition-all duration-300 shadow-lg shadow-red-500/25
                  hover:shadow-xl hover:shadow-red-500/35
                  focus:outline-none focus:ring-2 focus:ring-red-400/50 focus:ring-offset-2"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

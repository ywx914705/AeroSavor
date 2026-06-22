import { create } from "zustand"
import type { Restaurant } from "../api/client"

export type ThinkingStepStatus = "running" | "done" | "error" | "decision" | "collaboration" | "delegation" | "quality_retry"

export interface ThinkingStep {
  agentKey: string   // 原始 key，如 "intent_parser"
  agent: string      // 显示标签，如 "理解需求"
  message: string
  status: ThinkingStepStatus
  startTime?: number  // agent_start 的时间戳
  duration?: number   // agent_done 时计算的耗时(ms)
  next?: string       // supervisor_decision 的 next_action
  justCompleted?: boolean  // running→done 时短暂为 true，触发完成闪烁
}

interface RouteInfo {
  walking?: { mode: string; duration_min: number; distance_m: number } | null
  driving?: { mode: string; duration_min: number; distance_m: number; tolls?: number } | null
  transit?: { mode: string; duration_min: number; distance_m: number; cost?: number } | null
  nav_url?: string
  destination_name?: string
}

interface ChatStore {
  sessionId: string
  messages: ChatMessage[]
  recommendations: Restaurant[]
  routeInfo: RouteInfo | null
  isStreaming: boolean
  userLocation: { lng: number; lat: number } | null
  favoriteIds: Set<string>
  sidebarOpen: boolean
  thinkingSteps: ThinkingStep[]
  thinkingVisible: boolean
  locationPromptPending: string | null   // 被拦截等待定位的消息（null=不弹窗，""=主动定位）
  locationDeclinedAt: number | null      // 上次明确拒绝定位的时间戳（毫秒）
  lastSSEEventAt: number | null          // 最近一次收到 SSE 事件的时间戳
  hasError: boolean                      // 本轮是否有 SSE error 事件

  setSessionId: (id: string) => void
  addMessage: (m: ChatMessage) => void
  updateMessage: (id: string, content: string) => void
  setMessages: (msgs: ChatMessage[]) => void
  setRecommendations: (rs: Restaurant[]) => void
  setRouteInfo: (ri: RouteInfo | null) => void
  setStreaming: (s: boolean) => void
  setUserLocation: (loc: { lng: number; lat: number } | null) => void
  toggleFavorite: (poiId: string) => void
  setFavoriteIds: (ids: Set<string>) => void
  setSidebarOpen: (open: boolean) => void
  addThinkingStep: (step: ThinkingStep) => void
  updateThinkingStep: (agent: string, update: Partial<ThinkingStep>) => void
  setThinkingVisible: (visible: boolean) => void
  clearThinkingSteps: () => void
  setLocationPromptPending: (msg: string | null) => void
  setLocationDeclinedAt: (ts: number | null) => void
  setLastSSEEventAt: (ts: number) => void
  setHasError: (err: boolean) => void
  reset: () => void
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp?: number
}

const genSessionId = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`

const STORAGE_KEY = "restaurant-agent-state"

function loadState(): Partial<ChatStore> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return {
      sessionId: parsed.sessionId || genSessionId(),
      favoriteIds: new Set(parsed.favoriteIds || []),
      locationDeclinedAt: parsed.locationDeclinedAt ?? null,
    }
  } catch {
    return null
  }
}

function saveState(state: Pick<ChatStore, "sessionId" | "favoriteIds" | "locationDeclinedAt">) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        sessionId: state.sessionId,
        favoriteIds: [...state.favoriteIds],
        locationDeclinedAt: state.locationDeclinedAt,
      }),
    )
  } catch {
    // silently ignore
  }
}

const saved = loadState()

export const useChatStore = create<ChatStore>((set, get) => ({
  sessionId: saved?.sessionId || genSessionId(),
  messages: [],
  recommendations: [],
  routeInfo: null,
  isStreaming: false,
  userLocation: null,
  favoriteIds: saved?.favoriteIds || new Set<string>(),
  sidebarOpen: false,
  thinkingSteps: [],
  thinkingVisible: false,
  locationPromptPending: null,
  locationDeclinedAt: saved?.locationDeclinedAt ?? null,
  lastSSEEventAt: null,
  hasError: false,

  setSessionId: (id) => {
    set({ sessionId: id })
    saveState({ sessionId: id, favoriteIds: get().favoriteIds, locationDeclinedAt: get().locationDeclinedAt })
  },
  addMessage: (m) =>
    set((s) => ({ messages: [...s.messages, { ...m, timestamp: Date.now() }] })),
  updateMessage: (id, content) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content } : m,
      ),
    })),
  setMessages: (msgs) => set({ messages: msgs }),
  setRecommendations: (rs) => set({ recommendations: rs }),
  setRouteInfo: (ri) => set({ routeInfo: ri }),
  setStreaming: (b) => set({ isStreaming: b }),
  setUserLocation: (loc) => set({ userLocation: loc }),
  setLocationPromptPending: (msg) => set({ locationPromptPending: msg }),
  setLocationDeclinedAt: (ts) => {
    set({ locationDeclinedAt: ts })
    saveState({ sessionId: get().sessionId, favoriteIds: get().favoriteIds, locationDeclinedAt: ts })
  },
  setLastSSEEventAt: (ts) => set({ lastSSEEventAt: ts }),
  setHasError: (err) => set({ hasError: err }),
  toggleFavorite: (poiId) => {
    const next = new Set(get().favoriteIds)
    if (next.has(poiId)) {
      next.delete(poiId)
    } else {
      next.add(poiId)
    }
    set({ favoriteIds: next })
    saveState({ sessionId: get().sessionId, favoriteIds: next, locationDeclinedAt: get().locationDeclinedAt })
  },
  setFavoriteIds: (ids) => set({ favoriteIds: ids }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  addThinkingStep: (step) => set((s) => {
    // 如果同 agentKey 已有 "running" 状态的步骤，先将其标记为 done（避免重复 running 残留）
    const steps = s.thinkingSteps.map((st) =>
      st.agentKey === step.agentKey && st.status === "running"
        ? { ...st, status: "done" as const, message: st.message + "（重试）", duration: st.startTime ? Date.now() - st.startTime : undefined }
        : st
    )
    return { thinkingSteps: [...steps, { ...step, startTime: step.startTime || Date.now() }] }
  }),
  updateThinkingStep: (agentKey: string, update: Partial<ThinkingStep>) => set((s) => {
    // Update the LAST matching step (most recent for this agentKey)
    let lastIdx = -1
    for (let i = s.thinkingSteps.length - 1; i >= 0; i--) {
      if (s.thinkingSteps[i].agentKey === agentKey) { lastIdx = i; break }
    }
    if (lastIdx === -1) return s
    // Calculate duration if status is changing to done
    const existing = s.thinkingSteps[lastIdx]
    const durationUpdate: Partial<ThinkingStep> = {}
    const completionUpdate: Partial<ThinkingStep> = {}
    if (update.status === "done" && existing.startTime) {
      durationUpdate.duration = Date.now() - existing.startTime
      // Set justCompleted flag when transitioning from running to done
      if (existing.status === "running") {
        completionUpdate.justCompleted = true
      }
    }
    return {
      thinkingSteps: s.thinkingSteps.map((st, i) =>
        i === lastIdx ? { ...st, ...update, ...durationUpdate, ...completionUpdate } : st
      ),
    }
  }),
  setThinkingVisible: (visible) => set({ thinkingVisible: visible }),
  clearThinkingSteps: () => set({ thinkingSteps: [], thinkingVisible: false, hasError: false }),
  reset: () => {
    const newId = genSessionId()
    set({
      sessionId: newId,
      messages: [],
      recommendations: [],
      routeInfo: null,
      isStreaming: false,
      thinkingSteps: [],
      thinkingVisible: false,
    })
    saveState({ sessionId: newId, favoriteIds: get().favoriteIds, locationDeclinedAt: get().locationDeclinedAt })
  },
}))

// 开发模式：暴露 store 到全局，方便控制台调试定位弹窗
if (import.meta.env.DEV) {
  ;(window as any).__chatStore = useChatStore
}

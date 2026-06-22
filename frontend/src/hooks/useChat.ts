import { useCallback, useEffect, useRef } from "react"
import { useChatStore } from "../store/chat"
import {
  streamChat,
  sendFeedback as apiFeedback,
  getFavorites,
  addFavorite,
  removeFavorite,
} from "../api/client"
import { agentLabels } from "../constants/agents"
import { isNearbyQuery } from "../utils/locationDetection"

/** Supervisor 决策方向的可读映射 */
const decisionLabels: Record<string, string> = {
  recommend_agent: "→ 生成推荐",
  search_agent: "→ 重新搜索",
  location_agent: "→ 换位置",
  format_response: "→ 输出结果",
}

export function useChat() {
  const {
    sessionId,
    messages,
    recommendations,
    isStreaming,
    userLocation,
    favoriteIds,
    addMessage,
    updateMessage,
    setRecommendations,
    setRouteInfo,
    setStreaming,
    toggleFavorite,
    setFavoriteIds,
    addThinkingStep,
    updateThinkingStep,
    setThinkingVisible,
    clearThinkingSteps,
    setLastSSEEventAt,
    setHasError,
  } = useChatStore()

  const abortControllerRef = useRef<AbortController | null>(null)

  // 初始化收藏列表
  useEffect(() => {
    getFavorites()
      .then((favs) => {
        const ids = new Set(favs.map((f) => f.poi_id))
        setFavoriteIds(ids)
      })
      .catch(() => {
        // 未登录或请求失败，静默
      })
  }, [setFavoriteIds])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isStreaming) return

      // 按需定位拦截：用户说"附近"但没有GPS时，弹出定位提示
      const currentLocation = useChatStore.getState().userLocation
      if (isNearbyQuery(content) && !currentLocation) {
        const { locationDeclinedAt, setLocationPromptPending } = useChatStore.getState()
        const DECLINE_TTL = 24 * 60 * 60 * 1000
        if (!(locationDeclinedAt && Date.now() - locationDeclinedAt < DECLINE_TTL)) {
          setLocationPromptPending(content)
          return
        }
      }

      const userMsgId = `u-${Date.now()}`
      addMessage({ id: userMsgId, role: "user", content })

      const aiMsgId = `a-${Date.now()}`
      addMessage({ id: aiMsgId, role: "assistant", content: "" })

      setStreaming(true)  // Set streaming guard FIRST to prevent race conditions
      clearThinkingSteps()
      setThinkingVisible(true)

      const abortController = new AbortController()
      abortControllerRef.current = abortController

      let aiMsgContent = ""

      try {
        const currentLocation = useChatStore.getState().userLocation
        for await (const ev of streamChat(
          {
            session_id: sessionId,
            message: content,
            user_location: currentLocation
              ? { ...currentLocation, coord_system: "gcj02" }
              : undefined,
          },
          abortController.signal,
        )) {
          // Track SSE connection health
          setLastSSEEventAt(Date.now())

          if (ev.type === "response" && ev.content) {
            aiMsgContent = ev.content
            updateMessage(aiMsgId, ev.content)
          } else if (ev.type === "recommendations" && ev.data) {
            setRecommendations(ev.data)
          } else if (ev.type === "route_info" && ev.route_info) {
            setRouteInfo(ev.route_info)
          } else if (ev.type === "error") {
            updateMessage(aiMsgId, `❌ 出错了：${ev.message ?? "未知错误"}`)
            setHasError(true)
            addThinkingStep({
              agentKey: "system",
              agent: "系统",
              message: ev.message ?? "未知错误",
              status: "error",
            })
          } else if (ev.type === "agent_start" && ev.agent) {
            const label = agentLabels[ev.agent] ?? ev.agent
            addThinkingStep({
              agentKey: ev.agent,
              agent: label,
              message: ev.message ?? "",
              status: "running",
              startTime: Date.now(),
            })
          } else if (ev.type === "agent_done" && ev.agent) {
            updateThinkingStep(ev.agent, {
              message: ev.message ?? "",
              status: "done",
            })
          } else if (ev.type === "supervisor_decision") {
            // Supervisor 决策 — 用 "decision" status 区分
            const nextAction = (ev as any).next as string | undefined
            addThinkingStep({
              agentKey: "supervisor",
              agent: agentLabels.supervisor,
              message: ev.reason ?? "策略调整",
              status: "decision",
              next: nextAction,
            })
          } else if (ev.type === "agent_degraded" && ev.agent) {
            // Agent 降级 — LLM 不可用，使用了规则/硬编码兜底
            const label = agentLabels[ev.agent] ?? ev.agent
            addThinkingStep({
              agentKey: ev.agent,
              agent: label,
              message: `${ev.message ?? ""}${ev.fallback_reason ? `（${ev.fallback_reason}）` : ""}`,
              status: "error",
            })
          } else if (ev.type === "collaboration" && ev.from) {
            const label = agentLabels[ev.from] ?? ev.from
            addThinkingStep({
              agentKey: ev.from,
              agent: label,
              message: ev.message ?? "",
              status: "collaboration",
            })
          } else if (ev.type === "quality_retry" && ev.reason) {
            addThinkingStep({
              agentKey: "quality_retry",
              agent: "优化策略",
              message: `${ev.reason} → ${ev.new_strategy ?? "换方向重搜"}`,
              status: "quality_retry",
            })
          } else if (ev.type === "agent_message" && ev.from && ev.to) {
            const fromLabel = agentLabels[ev.from] ?? ev.from
            const toLabel = agentLabels[ev.to] ?? ev.to
            addThinkingStep({
              agentKey: `${ev.from}_to_${ev.to}`,
              agent: `${fromLabel} → ${toLabel}`,
              message: ev.message ?? (ev as any).reason ?? "",
              status: "collaboration",
            })
          } else if (ev.type === "delegation" && ev.from && ev.to) {
            const fromLabel = agentLabels[ev.from] ?? ev.from
            const toLabel = agentLabels[ev.to] ?? ev.to
            addThinkingStep({
              agentKey: `delegation_${ev.from}_${ev.to}`,
              agent: `${fromLabel} 委派 ${toLabel}`,
              message: (ev as any).task ?? (ev as any).reason ?? "",
              status: "delegation",
            })
          }
        }
      } finally {
        abortControllerRef.current = null
        // Mark running steps as "done". Non-running special statuses
        // (decision, collaboration, delegation, quality_retry) are instantaneous
        // events — keep their status for visual distinction, just calculate duration.
        const steps = useChatStore.getState().thinkingSteps
        const updates = steps.map((st) => {
          if (st.status === "running") {
            // Running steps that never got agent_done → force complete
            return {
              ...st,
              status: "done" as const,
              message: st.message || "已完成",
              duration: st.startTime ? Date.now() - st.startTime : undefined,
            }
          }
          // Non-running, non-done steps: keep their status but ensure duration
          if (st.status !== "done" && st.startTime && !st.duration) {
            return { ...st, duration: Date.now() - st.startTime }
          }
          return st
        })
        // Single batched update — avoid O(n) re-renders
        useChatStore.setState({ thinkingSteps: updates })
        setStreaming(false)
        setTimeout(() => setThinkingVisible(false), 8000)
      }
    },
    [
      sessionId,
      isStreaming,
      userLocation,
      addMessage,
      updateMessage,
      setRecommendations,
      setRouteInfo,
      setStreaming,
      addThinkingStep,
      updateThinkingStep,
      setThinkingVisible,
      clearThinkingSteps,
    ],
  )

  const stopGeneration = useCallback(() => {
    abortControllerRef.current?.abort()
  }, [])

  const sendFeedback = useCallback(
    async (poiId: string, poiName: string, action: string) => {
      try {
        await apiFeedback(sessionId, poiId, poiName, action)
      } catch (e) {
        console.warn("feedback failed", e)
      }
    },
    [sessionId],
  )

  const handleToggleFavorite = useCallback(
    async (poiId: string, poiName: string) => {
      const isFav = favoriteIds.has(poiId)
      toggleFavorite(poiId)
      try {
        if (isFav) {
          await removeFavorite(poiId)
        } else {
          await addFavorite(poiId, poiName)
          await sendFeedback(poiId, poiName, "liked")
        }
      } catch (e) {
        toggleFavorite(poiId)
        console.warn("favorite toggle failed", e)
      }
    },
    [favoriteIds, toggleFavorite, sendFeedback],
  )

  return {
    sessionId,
    messages,
    recommendations,
    isStreaming,
    favoriteIds,
    sendMessage,
    stopGeneration,
    sendFeedback,
    toggleFavorite: handleToggleFavorite,
  }
}

/** 后端通信封装：fetch + SSE 流。*/

export interface Restaurant {
  id: string
  name: string
  rating: number
  cost: number
  distance: number
  address: string
  type: string
  reason: string
  highlight: string
  suitable_for: string
  amap_url: string
  photos: string[]
  location: string
}

export interface SSEEvent {
  type: "response" | "recommendations" | "route_info" | "error" | "agent_start" | "agent_done" | "agent_degraded" | "collaboration" | "supervisor_decision" | "quality_retry" | "agent_message" | "delegation" | "heartbeat"
  content?: string
  data?: Restaurant[]
  route_info?: RouteInfoPayload
  message?: string
  agent?: string
  from?: string
  to?: string
  reason?: string
  next?: string
  new_strategy?: string
  task?: string
  fallback_reason?: string
}

export interface RouteInfoPayload {
  walking?: { mode: string; duration_min: number; distance_m: number } | null
  driving?: { mode: string; duration_min: number; distance_m: number; tolls?: number } | null
  transit?: { mode: string; duration_min: number; distance_m: number; cost?: number } | null
  nav_url?: string
  destination_name?: string
}

export interface ChatRequestBody {
  session_id: string
  message: string
  /** 前端 useLocation 已将浏览器 GPS（WGS-84）转为高德 GCJ-02，
   *  这里显式声明 coord_system，否则后端默认按 wgs84 会再次偏移 ~500m。 */
  user_location?: { lng: number; lat: number; coord_system?: "wgs84" | "gcj02" }
}

const API_BASE = "/api"

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handleResponse<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error")
    throw new ApiError(resp.status, text)
  }
  return resp.json()
}

export async function* streamChat(body: ChatRequestBody, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  const resp = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  })

  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error")
    throw new ApiError(resp.status, text)
  }

  if (!resp.body) throw new Error("No body in response")

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 用 \n\n 分隔事件
    const events = buffer.split("\n\n")
    buffer = events.pop() ?? ""

    for (const ev of events) {
      const line = ev.split("\n").find((l) => l.startsWith("data: "))
      if (!line) continue
      const payload = line.slice(6)
      if (payload === "[DONE]") return
      try {
        yield JSON.parse(payload) as SSEEvent
      } catch (e) {
        console.warn("Parse SSE failed", payload, e)
      }
    }
  }
}

export async function sendFeedback(
  sessionId: string,
  poiId: string,
  poiName: string,
  action: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      poi_id: poiId,
      poi_name: poiName,
      action,
    }),
  })
  await handleResponse(resp)
}

export async function addFavorite(
  poiId: string,
  poiName: string,
  note?: string,
): Promise<{ status: string; action: string }> {
  const resp = await fetch(`${API_BASE}/favorites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ poi_id: poiId, poi_name: poiName, note }),
  })
  return handleResponse(resp)
}

export async function removeFavorite(
  poiId: string,
): Promise<{ status: string; action: string }> {
  const resp = await fetch(`${API_BASE}/favorites`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ poi_id: poiId }),
  })
  return handleResponse(resp)
}

export async function getFavorites(): Promise<
  { poi_id: string; poi_name: string; created_at: string; note: string | null }[]
> {
  const resp = await fetch(`${API_BASE}/favorites`)
  return handleResponse(resp)
}

export async function getHistory(
  limit = 20,
): Promise<{ id: string; created_at: string; last_message: string; title: string | null; turn_count: number }[]> {
  const resp = await fetch(`${API_BASE}/history?limit=${limit}`)
  return handleResponse(resp)
}

export async function getSessionMessages(
  sessionId: string,
): Promise<{
  id: string
  created_at: string
  updated_at: string
  turn_count: number
  messages: { role: string; content: string; ts?: string }[]
}> {
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}`)
  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text().catch(() => "Unknown error"))
  }
  return resp.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" })
  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text().catch(() => "Unknown error"))
  }
}

export async function renameSession(
  sessionId: string,
  title: string,
): Promise<{ status: string; title: string }> {
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text().catch(() => "Unknown error"))
  }
  return resp.json()
}

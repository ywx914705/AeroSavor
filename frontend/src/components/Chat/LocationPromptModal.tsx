import { useState } from "react"
import { useChatStore } from "../../store/chat"
import { requestGeolocation, isGeolocationAvailable } from "../../hooks/useLocation"
import { useChat } from "../../hooks/useChat"

/**
 * 按需定位弹窗：当用户发"附近"类请求且没有GPS时弹出。
 * 引导用户授权定位，授权成功后自动发送被拦截的消息。
 */
export function LocationPromptModal() {
  const locationPromptPending = useChatStore((s) => s.locationPromptPending)
  const setLocationPromptPending = useChatStore((s) => s.setLocationPromptPending)
  const setLocationDeclinedAt = useChatStore((s) => s.setLocationDeclinedAt)
  const setUserLocation = useChatStore((s) => s.setUserLocation)

  const { sendMessage } = useChat()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (locationPromptPending === null) return null

  const isProactive = locationPromptPending === ""  // 用户主动点击定位（非消息拦截）
  const geoAvailable = isGeolocationAvailable()

  const handleClose = () => {
    setLocationPromptPending(null)
    setError(null)
    setLoading(false)
  }

  const handleDecline = () => {
    setLocationDeclinedAt(Date.now())
    // 如果有被拦截的消息，继续发送（不带定位）
    if (!isProactive) {
      sendMessage(locationPromptPending)
    }
    handleClose()
  }

  const handleAllow = async () => {
    setLoading(true)
    setError(null)
    try {
      const gcj = await requestGeolocation()
      setUserLocation(gcj)
      // 授权成功：如果有被拦截的消息，发送（带定位）
      if (!isProactive) {
        setLocationPromptPending(null)
        setLoading(false)
        sendMessage(locationPromptPending)
      } else {
        handleClose()
      }
    } catch (err: any) {
      setLoading(false)
      // 区分错误类型
      if (err?.message === "HTTPS_REQUIRED") {
        setError("当前非安全连接（HTTP），浏览器不允许获取位置。请使用 HTTPS 访问。")
      } else if (err?.code === 1) {
        // PERMISSION_DENIED
        setError("定位权限被拒绝。请在浏览器设置中允许本站获取位置。")
      } else if (err?.code === 2) {
        // POSITION_UNAVAILABLE
        setError("无法获取位置信息，请检查设备定位服务是否开启。")
      } else if (err?.code === 3) {
        // TIMEOUT
        setError("定位超时，请检查网络或GPS信号后重试。")
      } else {
        setError("定位失败，请稍后重试。")
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={handleDecline}
      />

      {/* 卡片 */}
      <div className="relative bg-white rounded-2xl p-7 w-[340px] shadow-2xl animate-pop-in">
        {/* 图标 */}
        <div className="mx-auto w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center mb-4 shadow-lg shadow-amber-200/50">
          {geoAvailable ? (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          ) : (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          )}
        </div>

        {/* 标题 */}
        <h3 className="text-lg font-bold text-slate-800 text-center mb-2">
          {geoAvailable
            ? (isProactive ? "开启定位，精准推荐" : "需要你的位置")
            : "需要安全连接"
          }
        </h3>

        {/* 说明 */}
        <p className="text-sm text-slate-500 text-center leading-relaxed mb-5">
          {geoAvailable
            ? (isProactive
              ? "开启定位后，搜索「附近」的餐厅会更精准，结果按距离排序。"
              : "为了推荐你附近的餐厅，我需要获取你的当前位置。仅用于搜索美食，不会存储位置信息。")
            : "浏览器要求 HTTPS 才能获取位置。当前是 HTTP 连接，无法使用定位功能。如果你在本地开发，请使用 localhost 访问。"
          }
        </p>

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 px-3 py-2 rounded-xl bg-red-50 border border-red-100 text-xs text-red-600 text-center leading-relaxed">
            {error}
          </div>
        )}

        {/* 按钮组 */}
        <div className="flex flex-col gap-2.5">
          {geoAvailable && (
            <button
              onClick={handleAllow}
              disabled={loading}
              className="w-full py-3 rounded-xl font-semibold text-white text-sm
                bg-gradient-to-r from-amber-500 to-orange-500
                hover:from-amber-600 hover:to-orange-600
                active:scale-[0.97] transition-all duration-200
                disabled:opacity-60 disabled:cursor-not-allowed
                shadow-lg shadow-amber-200/50"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  正在获取位置...
                </span>
              ) : "开启定位"}
            </button>
          )}

          <button
            onClick={handleDecline}
            className="w-full py-2.5 rounded-xl text-sm text-slate-400 font-medium
              hover:text-slate-600 hover:bg-slate-50 transition-all duration-200"
          >
            {isProactive ? "暂不开启" : "不用了，直接搜索"}
          </button>
        </div>
      </div>
    </div>
  )
}

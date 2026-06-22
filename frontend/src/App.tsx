import { ChatWindow } from "./components/Chat/ChatWindow"
import { useLocation } from "./hooks/useLocation"

export function App() {
  // 自动尝试获取浏览器定位（生产环境需要 HTTPS）
  useLocation()
  return <ChatWindow />
}

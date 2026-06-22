/** Agent 相关共享常量 */

export const agentLabels: Record<string, string> = {
  intent_parser:   "理解需求",
  location_agent:  "确认位置",
  memory_agent:    "读取偏好",
  get_weather:     "查询天气",
  search_agent:    "搜索餐厅",
  recommend_agent: "生成推荐",
  route_agent:     "规划路线",
  chat_agent:      "生成回复",
  supervisor:      "优化策略",
  format_response: "格式化回复",
}

export const agentIcons: Record<string, string> = {
  intent_parser:   "💭",
  location_agent:  "📍",
  memory_agent:    "📋",
  get_weather:     "🌤️",
  search_agent:    "🔍",
  recommend_agent: "⭐",
  route_agent:     "🗺️",
  chat_agent:      "💬",
  supervisor:      "💡",
  format_response: "✍️",
}

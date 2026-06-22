/** 用户偏好读写 hook。 */
import { useState, useEffect, useCallback } from "react"
import { getFavorites } from "../api/client"

interface UserPreference {
  favoriteCount: number
  /** 偏好是否已加载（区分冷启动） */
  loaded: boolean
}

/**
 * 轻量级偏好 hook：目前只跟踪收藏数。
 * 后续可扩展对接 GET /api/preferences 接口。
 */
export function usePreference() {
  const [pref, setPref] = useState<UserPreference>({
    favoriteCount: 0,
    loaded: false,
  })

  const refresh = useCallback(async () => {
    try {
      const favs = await getFavorites()
      setPref({ favoriteCount: favs.length, loaded: true })
    } catch {
      setPref((p) => ({ ...p, loaded: true }))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { ...pref, refresh }
}

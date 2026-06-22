import { useEffect } from "react"
import { useChatStore } from "../store/chat"

/**
 * WGS-84 → GCJ-02 坐标偏移（中国境内约 500m 偏差）。
 * 简化版 JS 实现，精度足够（误差 < 10m）。
 */
const PI = Math.PI
const A = 6378245.0
const EE = 0.00669342162296594323

function outOfChina(lng: number, lat: number): boolean {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function _transformLat(lng: number, lat: number): number {
  let ret =
    -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * Math.sqrt(Math.abs(lng))
  ret += ((20.0 * Math.sin(6.0 * lng * PI) + 20.0 * Math.sin(2.0 * lng * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(lat * PI) + 40.0 * Math.sin((lat / 3.0) * PI)) * 2.0) / 3.0
  ret += ((160.0 * Math.sin((lat / 12.0) * PI) + 320 * Math.sin((lat * PI) / 30.0)) * 2.0) / 3.0
  return ret
}

function _transformLng(lng: number, lat: number): number {
  let ret =
    300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * Math.sqrt(Math.abs(lng))
  ret += ((20.0 * Math.sin(6.0 * lng * PI) + 20.0 * Math.sin(2.0 * lng * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(lng * PI) + 40.0 * Math.sin((lng / 3.0) * PI)) * 2.0) / 3.0
  ret += ((150.0 * Math.sin((lng / 12.0) * PI) + 300.0 * Math.sin((lng / 30.0) * PI)) * 2.0) / 3.0
  return ret
}

export function wgs84ToGcj02(lng: number, lat: number): { lng: number; lat: number } {
  if (outOfChina(lng, lat)) return { lng, lat }
  let dlat = _transformLat(lng - 105.0, lat - 35.0)
  let dlng = _transformLng(lng - 105.0, lat - 35.0)
  const radlat = (lat / 180.0) * PI
  let magic = Math.sin(radlat)
  magic = 1 - EE * magic * magic
  const sqrtmagic = Math.sqrt(magic)
  dlat = (dlat * 180.0) / (((A * (1 - EE)) / (magic * sqrtmagic)) * PI)
  dlng = (dlng * 180.0) / ((A / sqrtmagic) * Math.cos(radlat) * PI)
  return { lng: lng + dlng, lat: lat + dlat }
}

/**
 * 浏览器 GPS 定位（WGS-84）→ 自动转为 GCJ-02 存入 store。
 * 后端收到的就是高德坐标系，无需再转。
 */
export function useLocation() {
  const setUserLocation = useChatStore((s) => s.setUserLocation)

  useEffect(() => {
    if (!("geolocation" in navigator)) return
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // 浏览器返回 WGS-84，转成高德 GCJ-02
        const gcj = wgs84ToGcj02(pos.coords.longitude, pos.coords.latitude)
        setUserLocation(gcj)
      },
      (err) => {
        console.warn("geolocation denied or failed:", err.message)
      },
      { timeout: 5000, enableHighAccuracy: false },
    )
  }, [setUserLocation])
}

/**
 * 检查浏览器是否支持定位且当前是安全上下文（HTTPS 或 localhost）。
 * HTTP 非localhost环境下浏览器会拒绝 geolocation API。
 */
export function isGeolocationAvailable(): boolean {
  if (!("geolocation" in navigator)) return false
  // 安全上下文检查：HTTPS、localhost、127.0.0.1 都允许
  if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
    return false
  }
  return true
}

/**
 * 命令式请求定位——供 LocationPromptModal 等组件调用。
 * 返回 GCJ-02 坐标，超时 8 秒。
 * 不安全上下文时直接 reject。
 */
export function requestGeolocation(): Promise<{ lng: number; lat: number }> {
  return new Promise((resolve, reject) => {
    if (!isGeolocationAvailable()) {
      reject(new Error("HTTPS_REQUIRED"))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const gcj = wgs84ToGcj02(pos.coords.longitude, pos.coords.latitude)
        resolve(gcj)
      },
      (err) => reject(err),
      { timeout: 8000, enableHighAccuracy: false },
    )
  })
}

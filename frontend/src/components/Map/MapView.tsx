import { useEffect, useRef, useState } from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import type { Restaurant } from "../../api/client"
import { useChatStore } from "../../store/chat"

import iconUrl from "leaflet/dist/images/marker-icon.png"
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png"
import shadowUrl from "leaflet/dist/images/marker-shadow.png"

// @ts-expect-error: private override
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })

interface Props {
  restaurants: Restaurant[]
  center?: string
}

const AMAP_TILE =
  "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"

function parseLatLng(loc: string | undefined): [number, number] | null {
  if (!loc) return null
  const [lng, lat] = loc.split(",").map(Number)
  if (Number.isNaN(lng) || Number.isNaN(lat)) return null
  return [lat, lng]
}

export function MapView({ restaurants, center }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)
  const userLocation = useChatStore((s) => s.userLocation)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const defaultCenter: [number, number] = userLocation
      ? [userLocation.lat, userLocation.lng]
      : [39.993, 116.473]
    const initialCenter = parseLatLng(center) ?? defaultCenter
    const map = L.map(containerRef.current, {
      center: initialCenter,
      zoom: 14,
      zoomControl: true,
      attributionControl: false,
    })
    L.tileLayer(AMAP_TILE, {
      subdomains: ["1", "2", "3", "4"],
      maxZoom: 19,
      attribution: "© AMap",
    }).addTo(map)
    mapRef.current = map
    layerRef.current = L.layerGroup().addTo(map)

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    const points: [number, number][] = []

    if (userLocation) {
      const userLL: [number, number] = [userLocation.lat, userLocation.lng]
      points.push(userLL)
      const userIcon = L.divIcon({
        className: "",
        html: `<div style="position:relative;">
          <div style="
            position:absolute;width:24px;height:24px;
            background:rgba(245,158,11,0.2);border-radius:50%;
            top:-4px;left:-4px;
            animation:pulse-ring 2s ease-out infinite;
          "></div>
          <div style="
            background:#F59E0B;color:white;
            width:16px;height:16px;border:3px solid white;
            border-radius:50%;
            box-shadow:0 0 0 2px #F59E0B, 0 2px 8px rgba(0,0,0,.15);
          "></div>
        </div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      })
      L.marker(userLL, { icon: userIcon, zIndexOffset: 1000 })
        .bindPopup('<div style="font-size:12px;font-weight:600;color:#D97706">你的位置</div>')
        .addTo(layer)
    }

    restaurants.forEach((r, i) => {
      const ll = parseLatLng(r.location)
      if (!ll) return
      points.push(ll)

      const colors = ["#F59E0B", "#EAB308", "#10B981", "#6366F1", "#EC4899"]
      const color = colors[i % colors.length]

      const html = `
        <div style="
          background:${color};color:white;
          width:30px;height:30px;display:flex;align-items:center;
          justify-content:center;font-weight:800;font-size:12px;font-family:Inter,sans-serif;
          border-radius:50%;
          border:2.5px solid white;box-shadow:0 2px 8px rgba(0,0,0,.15);
        ">${i + 1}</div>`
      const icon = L.divIcon({ className: "", html, iconSize: [30, 30], iconAnchor: [15, 15] })
      L.marker(ll, { icon })
        .bindPopup(
          `<div style="font-size:12px;line-height:1.6;padding:4px 0">
             <strong style="font-size:13px;color:#0F172A">${r.name}</strong><br/>
             <span style="color:#64748B">⭐ ${r.rating || "—"} · ¥${r.cost || "—"} · ${r.distance}m</span><br/>
             <a href="${r.amap_url}" target="_blank" style="display:inline-block;margin-top:4px;color:#D97706;font-weight:600;text-decoration:underline">查看详情 →</a>
           </div>`,
        )
        .addTo(layer)
    })

    if (points.length > 0) {
      const bounds = L.latLngBounds(points)
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 })
    } else if (center) {
      const c = parseLatLng(center)
      if (c) map.setView(c, 14)
    }
  }, [restaurants, center, userLocation])

  useEffect(() => {
    if (!collapsed && mapRef.current) {
      requestAnimationFrame(() => { mapRef.current?.invalidateSize() })
    }
  }, [collapsed])

  return (
    <div className="relative rounded-2xl overflow-hidden border border-slate-100/80 shadow-md map-glow-wrap transition-shadow duration-500 hover:shadow-lg">
      {/* Controls */}
      <div className="absolute top-3 left-3 z-[1000] flex items-center gap-2">
        <span className="px-3 py-1.5 glass-strong rounded-full text-xs text-slate-700 font-bold shadow-sm
          flex items-center gap-1.5">
          <svg width="11" height="11" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
            <path d="M5 1a3 3 0 013 3c0 2.25-3 5-3 5S2 6.25 2 4a3 3 0 013-3z" />
            <circle cx="5" cy="4" r="1" />
          </svg>
          地图
        </span>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="px-2.5 py-1.5 glass-strong rounded-full text-xs text-slate-500 shadow-sm font-semibold
            hover:text-amber-600 transition-all duration-200"
          aria-label={collapsed ? "展开地图" : "收起地图"}
        >
          {collapsed ? "展开" : "收起"}
        </button>
      </div>

      {restaurants.length > 0 && (
        <div className="absolute top-3 right-3 z-[1000]">
          <span className="glass-strong rounded-full px-3 py-1.5 text-xs text-amber-600 font-bold shadow-sm">
            {restaurants.length} 家餐厅
          </span>
        </div>
      )}

      <div
        ref={containerRef}
        className="overflow-hidden transition-[height] duration-500 ease-out relative z-10"
        style={{ height: collapsed ? 52 : 280, width: "100%" }}
      />
    </div>
  )
}

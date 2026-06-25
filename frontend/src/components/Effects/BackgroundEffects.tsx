import { useMemo } from "react"

/**
 * 轻量噪点纹理 —— 一次性生成一张小尺寸 data-URI，作为 CSS 背景平铺。
 *
 * 旧实现用每帧 createImageData 重绘全屏 Canvas（~830w 像素 × 15次/秒），
 * 是流式输出卡顿的主要主线程占用源。改成静态纹理后画质几乎无损、零运行时开销。
 */
function GrainOverlay() {
  const dataUri = useMemo(() => {
    const size = 128 // 小尺寸 + background-repeat 即可覆盖全屏
    const canvas = document.createElement("canvas")
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext("2d")
    if (!ctx) return ""
    const imageData = ctx.createImageData(size, size)
    const data = imageData.data
    for (let i = 0; i < data.length; i += 4) {
      const v = Math.random() * 255
      data[i] = v
      data[i + 1] = v
      data[i + 2] = v
      data[i + 3] = 12 // 极低透明度
    }
    ctx.putImageData(imageData, 0, 0)
    return canvas.toDataURL()
  }, [])

  if (!dataUri) return null
  return (
    <div
      className="grain-texture"
      style={{
        backgroundImage: `url(${dataUri})`,
        backgroundRepeat: "repeat",
      }}
    />
  )
}

export function BackgroundEffects() {
  return (
    <>
      <GrainOverlay />
    </>
  )
}

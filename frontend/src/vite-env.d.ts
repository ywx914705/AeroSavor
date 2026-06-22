/// <reference types="vite/client" />

// 图片资源类型声明
declare module "*.png" {
  const src: string
  export default src
}
declare module "*.jpg" {
  const src: string
  export default src
}
declare module "*.svg" {
  const src: string
  export default src
}

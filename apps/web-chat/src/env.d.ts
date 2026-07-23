/// <reference types="vite/client" />

// Vue SFC 类型声明
// 官方推荐的写法用 {}（空对象字面量），被 @typescript-eslint/no-empty-object-type
// 误报；本文件即 Vue 3 标准 .vue shim 写法，加行内 eslint-disable 抑制
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/ban-types
  const component: DefineComponent<{}, {}, any>
  export default component
}

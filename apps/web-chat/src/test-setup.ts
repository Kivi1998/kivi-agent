// vitest 公共测试 setup：jsdom 缺失的浏览器 API stub
// ECharts / VChart 在 autoresize=true 时创建 ResizeObserver；
// jsdom 不内置，需要在此桩一下
// 模式参考：vue-echarts 官方测试建议

// ResizeObserver 桩
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver
}

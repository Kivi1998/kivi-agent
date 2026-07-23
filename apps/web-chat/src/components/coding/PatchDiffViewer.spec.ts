// PatchDiffViewer 组件测试（3 场景：空 / 1 patch / 2 patch + 切换）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PatchDiffViewer from './PatchDiffViewer.vue'
import type { PatchRecord } from '@/types/api'

const patch1: PatchRecord = {
  patch_id: 'p-1',
  iteration: 1,
  file_path: 'mymod.py',
  hunks_proposed: 1,
  hunks_applied: 1,
  diff: '@@ -1,1 +1,1 @@\n-# empty\n+def add(a, b): return a + b\n',
  ts: '2026-07-23T00:00:02Z'
}

const patch2: PatchRecord = {
  patch_id: 'p-2',
  iteration: 2,
  file_path: 'mymod.py',
  hunks_proposed: 2,
  hunks_applied: 1,
  diff: '@@ -3,1 +3,2 @@\n-def add(a, b):\n+def add(a: int, b: int) -> int:\n+    return a + b\n',
  ts: '2026-07-23T00:00:06Z'
}

describe('PatchDiffViewer', () => {
  it('空：显示 "暂无 patch" empty state + 不渲染 tabs / pre', () => {
    const wrapper = mount(PatchDiffViewer, { props: { patches: [] } })
    expect(wrapper.find('[data-testid="patch-diff-viewer"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="patch-diff-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="patch-diff-tabs"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="patch-diff-pre"]').exists()).toBe(false)
  })

  it('1 patch：渲染 1 个 tab + 1 个 pre + add/remove/meta 分行着色', () => {
    const wrapper = mount(PatchDiffViewer, { props: { patches: [patch1] } })
    expect(wrapper.findAll('[data-testid^="patch-tab-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="patch-diff-pre"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="patch-diff-meta"]').text()).toContain(
      'mymod.py'
    )
    // add 行 / remove 行 / meta 行
    expect(wrapper.findAll('[data-testid="patch-diff-pre"] .pd-line-add')).toHaveLength(
      1
    )
    expect(
      wrapper.findAll('[data-testid="patch-diff-pre"] .pd-line-remove')
    ).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="patch-diff-pre"] .pd-line-meta')).toHaveLength(
      1
    )
  })

  it('多 patch：tabs 切换 + 第二次切到 patch2 显示 hunks 1/2 + 文件名', async () => {
    const wrapper = mount(PatchDiffViewer, { props: { patches: [patch1, patch2] } })
    expect(wrapper.findAll('[data-testid^="patch-tab-"]')).toHaveLength(2)
    // 默认显示 patch1
    expect(wrapper.find('[data-testid="patch-tab-0"]').classes()).toContain('active')
    expect(wrapper.find('[data-testid="patch-tab-1"]').classes()).not.toContain(
      'active'
    )

    // 切换到 patch2
    await wrapper.find('[data-testid="patch-tab-1"]').trigger('click')
    expect(wrapper.find('[data-testid="patch-tab-0"]').classes()).not.toContain(
      'active'
    )
    expect(wrapper.find('[data-testid="patch-tab-1"]').classes()).toContain('active')
    // patch2 文本中的 "1/2" 出现
    expect(wrapper.find('[data-testid="patch-tab-1"]').text()).toContain('1/2')
    expect(wrapper.find('[data-testid="patch-diff-meta"]').text()).toContain('iter: 2')
  })
})

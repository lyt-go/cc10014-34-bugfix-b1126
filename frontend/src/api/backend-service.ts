import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  AcceptanceResult,
  ActionResult,
  CraftClearance,
  EntryRow,
  OverviewResult,
  PageResult,
  ReconsiderationScope,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function requestReconsideration(
  reviewId: number,
  craft: string,
  remark = '',
): Promise<ActionResult> {
  const response = await request(`/api/expert_review/${reviewId}/reconsideration`, {
    method: 'POST',
    body: JSON.stringify({ craft, remark }),
  })
  return await response.json()
}

export async function fetchReconsiderationScope(
  planId: number,
): Promise<ReconsiderationScope> {
  const response = await request(`/api/restoration_plan/${planId}/reconsideration-scope`)
  if (!response.ok) throw new Error('复议范围读取失败')
  return await response.json()
}

export async function fetchApprovalPreview(planId: number): Promise<ReconsiderationScope> {
  const response = await request(`/api/restoration_plan/${planId}/approval-preview`)
  if (!response.ok) throw new Error('审批范围读取失败')
  return await response.json()
}

export async function fetchCraftClearance(
  planId: number,
  craft: string,
): Promise<CraftClearance> {
  const response = await request(
    `/api/restoration_plan/${planId}/craft-clearance?craft=${encodeURIComponent(craft)}`,
  )
  if (!response.ok) throw new Error('工艺凭据读取失败')
  return await response.json()
}

export async function issueWorkfront(
  planId: number,
  craft: string,
  recipient: string,
  note = '',
): Promise<AcceptanceResult> {
  const response = await request(`/api/restoration_plan/${planId}/workfront`, {
    method: 'POST',
    body: JSON.stringify({ craft, recipient, note }),
  })
  return await response.json()
}

export async function completeWorkfront(
  planId: number,
  workfrontId: number,
): Promise<AcceptanceResult> {
  const response = await request(`/api/restoration_plan/${planId}/workfront/complete`, {
    method: 'POST',
    body: JSON.stringify({ workfront_id: workfrontId }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

export type DependentStatus = {
  module: string
  entry_id: number
  entry: Record<string, unknown>
  upstream: { module: string; id: number; name: string; status: string }[]
  downstream: { module: string; id: number; name: string; status: string }[]
}

export async function fetchDependentStatus(
  moduleKey: string,
  entryId: number,
): Promise<DependentStatus> {
  const response = await request(`/api/cross-module/dependent-status/${moduleKey}/${entryId}`)
  if (!response.ok) throw new Error('跨模块状态查询失败')
  return await response.json()
}

export async function fetchDependencyGraph(): Promise<{ nodes: unknown[]; edges: unknown[] }> {
  const response = await request('/api/cross-module/dependency-graph')
  if (!response.ok) throw new Error('依赖图加载失败')
  return await response.json()
}

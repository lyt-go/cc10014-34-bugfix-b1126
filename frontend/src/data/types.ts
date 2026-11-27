/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type ScopeBasis = {
  工艺: string
  意见ID: number
  专家: string
  结论?: string
  修改建议?: string
  审批批次?: number
  状态?: string
}

export type PendingScope = {
  工艺: string
  意见ID: number
  专家: string
  状态: string
  复议回执: string
  原结论?: string
  发起时间?: string
}

export type ReviewBoardItem = {
  意见ID: number
  专家: string
  专业领域: string
  工艺: string
  评审结论: string
  评审状态: string
  范围状态: string
  复议回执: string
  依据仍有效: boolean
}

export type ReconsiderationReceipt = {
  回执编号: string
  意见ID: number
  专家: string
  工艺: string
  评审结论?: string
  修改建议?: string
  发起时间?: string
  状态?: string
}

export type WorkfrontRecord = {
  id: number
  作业面: string
  工艺: string
  领取人: string
  领取时间: string
  审批批次: number
  依据意见ID: number
  依据专家: string
  状态: string
  依据快照?: ScopeBasis
}

export type ReconsiderationScope = {
  plan_id: number
  方案编号: string
  plan_status: string
  approval_in_flight: boolean
  approval_batch: number
  plan_crafts: string[]
  valid_bases: ScopeBasis[]
  valid_crafts: string[]
  pending_reviews: PendingScope[]
  pending_crafts: string[]
  approval_candidates: ScopeBasis[]
  receipts: ReconsiderationReceipt[]
  last_approval_bases: ScopeBasis[]
  workfronts: WorkfrontRecord[]
  review_board: {
    items: ReviewBoardItem[]
    pending_crafts: string[]
    valid_crafts: string[]
    receipts: ReconsiderationReceipt[]
  }
  message: string
}

export type CraftClearance = {
  craft: string
  state: '有效' | '待重新审核' | '未批准' | '未覆盖'
  covered: boolean
  approved: boolean
  pending: boolean
  basis: ScopeBasis | null
  pending_review: PendingScope | null
  approval_batch: number
  plan_status: string
  valid_crafts: string[]
  pending_crafts: string[]
}

export type AcceptanceResult = {
  ok: boolean
  message: string
  entry: Record<string, unknown> | null
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

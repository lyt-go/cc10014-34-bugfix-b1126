<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-testid="`row-${row.id}`"
          :data-status="String(row.status)"
        >
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <section
      v-if="isPlan && scope"
      class="scope-panel"
      data-testid="reconsideration-scope"
    >
      <header class="scope-head">
        <h3>复议范围与现场凭据</h3>
        <span class="scope-status" :data-plan-status="scope.plan_status">
          {{ scope.plan_status }} · 审批批次 {{ scope.approval_batch }}
        </span>
      </header>
      <p class="scope-note">{{ scope.message }}</p>
      <div class="scope-grid">
        <div>
          <h4>评审意见与范围</h4>
          <table class="data-table">
            <thead>
              <tr><th>专家</th><th>工艺</th><th>评审状态</th><th>范围状态</th><th>复议回执</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in scope.review_board.items" :key="item.意见ID">
                <td>{{ item.专家 }}</td>
                <td>{{ item.工艺 }}</td>
                <td>{{ item.评审状态 }}</td>
                <td :data-scope-state="item.范围状态">{{ item.范围状态 }}</td>
                <td>{{ item.复议回执 || '—' }}</td>
              </tr>
              <tr v-if="!scope.review_board.items.length">
                <td colspan="5" class="empty-state">暂无评审意见</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h4>现场领取作业面</h4>
          <div class="scope-form">
            <label>
              <span>工艺</span>
              <input v-model="workfrontCraft" data-testid="workfront-craft" placeholder="如 石作" />
            </label>
            <label>
              <span>领取人</span>
              <input v-model="workfrontRecipient" data-testid="workfront-recipient" placeholder="施工方" />
            </label>
            <button class="btn" data-testid="check-clearance" type="button" @click="checkClearance">
              查询凭据
            </button>
            <button class="btn primary" data-testid="issue-workfront" type="button" @click="issueWorkfrontRow">
              领取作业面
            </button>
          </div>
          <p v-if="clearance" class="scope-note" :data-clearance="clearance.state">
            {{ clearance.craft }}：{{ clearance.state }}
            <template v-if="clearance.basis">
              （意见#{{ clearance.basis.意见ID }}·{{ clearance.basis.专家 }}，审批批次{{ clearance.basis.审批批次 }}）
            </template>
            <template v-else-if="clearance.pending_review">
              （回执{{ clearance.pending_review.复议回执 }}指向意见#{{ clearance.pending_review.意见ID }}）
            </template>
          </p>
          <ul class="workfront-list">
            <li v-for="item in scope.workfronts" :key="item.id">
              {{ item.作业面 }} · {{ item.领取人 }} · {{ item.状态 }} · 依据意见#{{ item.依据意见ID }}
              <button
                v-if="item.状态 === '已受理'"
                class="link"
                type="button"
                @click="completeWorkfrontRow(item.id)"
              >
                完成交接
              </button>
            </li>
            <li v-if="!scope.workfronts.length" class="empty-state">尚未领取作业面</li>
          </ul>
        </div>
      </div>
    </section>

    <div v-if="showReconsider" class="modal-backdrop" data-testid="reconsider-modal">
      <form class="modal" @submit.prevent="submitReconsider">
        <h3>发起复议</h3>
        <p class="page-desc">
          指向意见 #{{ reconsiderTarget?.id }}（{{ reconsiderTarget?.专家姓名 }}）。
          复议只重审填写的工艺范围，其他专家结论继续有效。
        </p>
        <label class="create-field">
          <span>工艺范围</span>
          <input v-model="reconsiderCraft" data-testid="reconsider-craft" required />
        </label>
        <label class="create-field">
          <span>复议说明</span>
          <input v-model="reconsiderRemark" data-testid="reconsider-remark" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showReconsider = false">取消</button>
          <button class="btn primary" data-testid="submit-reconsider" type="submit">提交复议</button>
        </div>
      </form>
    </div>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchCraftClearance,
  completeWorkfront,
  createEntry,
  downloadEntries,
  fetchReconsiderationScope,
  issueWorkfront,
  listEntries,
  moduleMeta,
  requestReconsideration,
  runAction as applyAction,
} from '@/api/backend-service'
import type { CraftClearance, EntryRow, ReconsiderationScope } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const isPlan = meta.key === 'restoration_plan'
const isReview = meta.key === 'expert_review'
const scope = ref<ReconsiderationScope | null>(null)
const workfrontCraft = ref('')
const workfrontRecipient = ref('')
const clearance = ref<CraftClearance | null>(null)
const showReconsider = ref(false)
const reconsiderTarget = ref<EntryRow | null>(null)
const reconsiderCraft = ref('')
const reconsiderRemark = ref('')

const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((r) => r.status === meta.statuses[1]).length },
  { label: meta.metrics[2], value: rows.value.filter((r) => r.status === meta.statuses[meta.statuses.length - 1]).length },
])

const statusSummary = computed(() =>
  meta.statuses.map((s) => ({ status: s, count: rows.value.filter((r) => String(r.status) === s).length })),
)

function resetFilters() { filters.value = {}; void reload() }

async function exportRows() {
  errorMessage.value = ''
  try { await downloadEntries(meta.key, filters.value) }
  catch (e) { errorMessage.value = e instanceof Error ? e.message : '导出失败' }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((f) => [f, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true; errorMessage.value = ''
  try {
    const r = await createEntry(meta.key, createValues.value)
    if (!r.ok) throw new Error(r.message)
    showCreate.value = false; await reload()
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '登记失败' }
  finally { creating.value = false }
}

async function loadScope(row?: EntryRow) {
  if (!isPlan) return
  const target = row ?? rows.value.find((r) => String(r.方案编号) === 'C-37') ?? rows.value[0]
  if (!target) { scope.value = null; return }
  try { scope.value = await fetchReconsiderationScope(Number(target.id)) }
  catch (e) { errorMessage.value = e instanceof Error ? e.message : '复议范围读取失败' }
}

async function checkClearance() {
  if (!scope.value) return
  errorMessage.value = ''
  try {
    clearance.value = await fetchCraftClearance(scope.value.plan_id, workfrontCraft.value)
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '凭据查询失败' }
}

async function issueWorkfrontRow() {
  if (!scope.value) return
  errorMessage.value = ''
  try {
    const r = await issueWorkfront(
      scope.value.plan_id, workfrontCraft.value, workfrontRecipient.value)
    if (!r.ok) throw new Error(r.message)
    await loadScope()
    await checkClearance()
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '领取失败' }
}

async function completeWorkfrontRow(id: number) {
  if (!scope.value) return
  errorMessage.value = ''
  try {
    const r = await completeWorkfront(scope.value.plan_id, id)
    if (!r.ok) throw new Error(r.message)
    await loadScope()
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '交接失败' }
}

async function submitReconsider() {
  if (!reconsiderTarget.value) return
  errorMessage.value = ''
  try {
    const r = await requestReconsideration(
      Number(reconsiderTarget.value.id), reconsiderCraft.value, reconsiderRemark.value)
    if (!r.ok) throw new Error(r.message)
    showReconsider.value = false
    await reload()
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '复议失败' }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  if (isReview && action === '发起复议') {
    reconsiderTarget.value = row
    reconsiderCraft.value = String(row['工艺范围'] ?? row['专业领域'] ?? '')
    reconsiderRemark.value = ''
    showReconsider.value = true
    return
  }
  try {
    const r = await applyAction(meta.key, Number(row.id), action)
    if (!r.ok) throw new Error(r.message)
    await reload()
    if (isPlan) await loadScope(rows.value.find((x) => x.id === row.id))
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '操作失败' }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items; total.value = payload.total
    if (isPlan) await loadScope()
  } catch (e) { errorMessage.value = e instanceof Error ? e.message : '业务列表读取失败' }
}

onMounted(reload)
</script>

<style scoped>
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); display:flex; align-items:center; justify-content:center; z-index:100; }
.modal { background:#fff; border-radius:8px; padding:24px; width:480px; max-height:80vh; overflow-y:auto; }
.create-field { display:flex; flex-direction:column; gap:4px; margin-bottom:12px; }
.create-field span { font-size:13px; color:var(--text-secondary,#4a5568); }
.create-field input { padding:6px 8px; border:1px solid var(--border-color,#e2e8f0); border-radius:4px; font-size:13px; }
.scope-panel { margin-top:16px; background:#fff; border:1px solid var(--border); border-radius:8px; padding:14px; }
.scope-head { display:flex; justify-content:space-between; align-items:center; }
.scope-head h3 { margin:0; font-size:15px; }
.scope-status { font-size:12px; color:var(--muted); }
.scope-note { font-size:12px; color:var(--muted); margin:6px 0 10px; }
.scope-grid { display:grid; grid-template-columns:1.4fr 1fr; gap:16px; }
.scope-grid h4 { font-size:13px; margin:0 0 8px; }
.scope-form { display:flex; flex-wrap:wrap; gap:8px; align-items:flex-end; margin-bottom:8px; }
.scope-form label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--muted); }
.scope-form input { padding:6px 8px; border:1px solid var(--border); border-radius:6px; font-size:13px; }
.workfront-list { list-style:none; padding:0; margin:8px 0 0; font-size:12px; color:var(--muted); }
.workfront-list li { padding:4px 0; border-bottom:1px solid #f0f2f5; }
</style>
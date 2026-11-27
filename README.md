# 古建筑修缮管理平台

文保工程师、工匠和监理共同管理古建筑修缮工序，审核修缮方案，签收变更后按确认版施工。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 建筑勘查 | `building_survey` | 勘查记录 | 建筑名称、勘查部位、病害类型 |
| 修缮方案 | `restoration_plan` | 修缮方案 | 方案编号、对应勘查、修缮工艺 |
| 材料核验 | `material_verify` | 材料核验单 | 材料名称、规格型号、供应商 |
| 工匠分配 | `craftsman_assign` | 工匠分配单 | 工匠姓名、技艺类别、资质等级 |
| 工序编排 | `work_sequence` | 工序卡 | 工序名称、前置工序、所需工匠 |
| 质量检查 | `quality_inspect` | 检查记录 | 检查工序、检查项目、技术标准 |
| 历史图纸 | `historical_drawing` | 历史图纸 | 图纸编号、绘制年代、绘制内容 |
| 构件登记 | `component_registry` | 构件档案 | 构件名称、所属建筑、材质类型 |
| 环境监测 | `env_monitor` | 监测数据 | 监测位置、温度读数、湿度读数 |
| 修缮日志 | `restoration_log` | 施工日志 | 施工日期、对应工序、施工内容 |
| 验收记录 | `acceptance_record` | 验收报告 | 验收工序、验收标准、验收结论 |
| 修缮支出 | `funding_use` | 支出记录 | 支出项目、支出类别、预算金额 |
| 档案归档 | `archive_mgmt` | 修缮档案 | 档案名称、档案类别、形成日期 |
| 专家评审 | `expert_review` | 评审意见 | 评审方案、专家姓名、专业领域 |
| 安全交底 | `safety_briefing` | 交底记录 | 交底工序、危险源、防护措施 |
| 施工排期 | `construction_schedule` | 排期计划 | 计划工序、开始日期、结束日期 |
| 变更签证 | `change_order` | 变更签证单 | 变更事项、变更原因、影响工序 |
| 竣工总结 | `completion_summary` | 竣工报告 | 修缮项目、开工日期、竣工日期 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：应用开发
子方向：web前端/全栈开发

## 专家复议与方案审批的工艺范围

复议不再整案驳回方案，而是指向一条具体的已汇总意见和它的工艺范围：

- `expert_review` 的「发起复议」只作用在被点名的评审意见上；同一条意见+工艺
  重复提交复用同一份回执（`RF-xxxx`），不会产生第二份。
- 方案的 `待审清单` 只加入被复议的工艺，其他工艺的有效依据原样保留；方案
  从「已通过」退成「部分通过」，不会变成「已驳回」。
- 方案审批结算本轮批准时，`本次批准有效工艺依据` 是本次批准的不可变快照，
  审批结果消息里同时列出仍有效的工艺和待重新审核的工艺（含回执号和意见号）。
- 施工现场按工艺查凭据：`GET /api/restoration_plan/{id}/craft-clearance?craft=石作`
  返回 `有效 / 待重新审核 / 未批准 / 未覆盖`；只有 `有效` 的工艺能领作业面。
- 复议前已经受理的作业面交接不会被追溯撤销，`workfront/complete` 仍可完成。

相关接口（均注册在 `/{module}` 动态路由之前）：

| 接口 | 用途 |
| --- | --- |
| `POST /api/expert_review/{id}/reconsideration` | 按意见+工艺发起复议，返回回执 |
| `GET /api/restoration_plan/{id}/reconsideration-scope` | 评审清单与方案审批共用的复议范围 |
| `GET /api/restoration_plan/{id}/approval-preview` | 本次批准会留下哪些有效依据 |
| `GET /api/restoration_plan/{id}/craft-clearance?craft=` | 现场按工艺查凭据 |
| `POST /api/restoration_plan/{id}/workfront` | 领取作业面（只接受有效凭据） |
| `POST /api/restoration_plan/{id}/workfront/complete` | 完成已受理交接 |

C-37 示例：方案 #4「木作：大木归安、木梁墩接；石作：台基石构件剔补」下，
甲（木作）与乙（石作）各有一条已汇总意见。对甲发起复议后，方案待审清单只有
木作，乙的石作结论仍可用于签材料和领取作业面。

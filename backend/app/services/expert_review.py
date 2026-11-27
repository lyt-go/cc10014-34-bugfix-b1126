"""专家评审领域服务：汇总意见后联动方案状态。

复议不再整案驳回：它必须指向一条已汇总意见和该意见的工艺范围，只在
方案的待审清单里加入这一道工艺，其余专家结论继续有效。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services import plan_scope
from app.store import store


class ExpertReviewService(BaseModuleService):
    MODULE = "expert_review"
    ENTITY = "评审意见"
    OPERATION_TERM = "开始评审"
    LIST_FIELDS = [
        "评审方案", "专家姓名", "专业领域", "工艺范围", "评审结论", "修改建议",
        "评审日期", "评审轮次", "备注说明",
    ]
    REQUIRED_FIELDS = ["评审方案", "专家姓名", "专业领域"]
    STATUS_ORDER = ["待评审", "评审中", "已汇总", "需复议"]
    ACTION_RULES = {"开始评审": "评审中", "汇总意见": "已汇总", "发起复议": "需复议"}
    NEGATIVE_ACTIONS = []

    # ── 复议指向：复议总是落在被点名的这条已汇总意见上 ──
    def _craft(self, entry: dict[str, Any]) -> str:
        raw = entry.get("工艺范围") or entry.get("专业领域", "")
        return plan_scope.canonical_craft(raw)

    def _plan_for(self, entry: dict[str, Any]):
        plan_id = str(entry.get("评审方案") or "")
        return store.find("restoration_plan", int(plan_id)) if plan_id.isdigit() else None

    def _legacy_auto_approval(
        self, plan: dict[str, Any], entry: dict[str, Any]
    ) -> bool:
        """多工艺方案必须由审批人按范围批准，不再由汇总意见自动整案通过。"""
        if entry.get("工艺范围"):
            return False
        return len(plan_scope.plan_crafts(plan)) <= 1

    def cross_module_verify(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> tuple[bool, str]:
        plan_id = entry.get("评审方案", "")
        if action == "开始评审":
            # 被评审的方案必须存在
            plan = store.find("restoration_plan", int(plan_id)) if plan_id.isdigit() else None
            if not plan:
                return False, f"评审方案#{plan_id}在系统中不存在"
            if plan.get("status") not in ("待审核", "已通过", "部分通过"):
                return False, f"方案#{plan_id}状态「{plan.get('status')}」不支持评审"
        if action == "汇总意见":
            # 汇总时方案必须仍在审核链路中
            plan = store.find("restoration_plan", int(plan_id)) if plan_id.isdigit() else None
            if plan and plan.get("status") not in ("待审核", "已通过", "部分通过"):
                return False, f"待评审方案#{plan_id}状态为{plan.get('status')}，不能汇总"

        if action == "发起复议":
            plan = self._plan_for(entry)
            if plan is None:
                return False, f"复议意见所属方案#{entry.get('评审方案')}不存在"
            craft = self._craft(entry)
            if not craft:
                return False, "复议必须指明工艺范围，才能对应到具体评审结论"
            repeat = entry.get("status") == "需复议" or bool(
                plan_scope.find_receipt(plan, int(entry.get("id", 0)), craft)
            )
            if entry.get("status") != "已汇总" and not repeat:
                return False, (
                    f"复议只能指向已汇总意见，意见#{entry.get('id')}当前状态"
                    f"「{entry.get('status')}」"
                )
            if not repeat and not plan_scope.craft_covered(plan, craft):
                return False, (
                    f"工艺范围「{craft}」不在方案"
                    f"#{plan.get('id')}的修缮工艺「{plan.get('修缮工艺', '')}」内"
                )
        return True, ""

    def cross_module_effect(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> list[dict]:
        effects = []
        if action == "汇总意见":
            plan = self._plan_for(entry)
            if plan:
                receipt = plan_scope.find_receipt(
                    plan, int(entry.get("id", 0)), self._craft(entry)
                )
                if receipt:
                    # 复议后的重新汇总：保留追溯，等审批人重新批准工艺
                    plan_scope.finalize_reconsideration(plan, entry)
                    effects.append(dict(plan))
                elif plan.get("status") == "待审核" and any(
                    str(r.get("评审方案")) == str(plan.get("id"))
                    and r.get("status") == "需复议"
                    for r in store.rows(self.MODULE)
                ):
                    # 复议在途时不做整案通过：等审批人按范围结算
                    pass
                elif plan.get("status") in ("已通过", "部分通过"):
                    # 方案已批准：新汇总意见只追加本工艺依据，其他工艺照旧
                    if plan_scope.extend_approval(plan, entry):
                        effects.append(dict(plan))
                elif plan.get("status") == "待审核" and self._legacy_auto_approval(plan, entry):
                    # 兼容原有审批入口：单一工艺方案的首轮汇总即推动方案批准
                    reviews = store.rows(self.MODULE)
                    scoped = [
                        r for r in reviews
                        if str(r.get("评审方案")) == str(plan.get("id"))
                    ]
                    plan_scope.apply_approval(plan, scoped, source="专家汇总")
                    pending = bool(plan.get("待审清单"))
                    plan["status"] = "部分通过" if pending else "已通过"
                    plan["pending"] = pending
                    plan["abnormal"] = False
                    effects.append(dict(plan))
                    survey_id = plan.get("对应勘查", "")
                    if survey_id:
                        survey = store.find("building_survey", int(survey_id)) if survey_id.isdigit() else None
                        if survey:
                            survey["status"] = "已复核"
                            survey["pending"] = False
                            effects.append(dict(survey))
        elif action == "发起复议":
            plan = self._plan_for(entry)
            if plan:
                # 被复议的意见本身转入需复议；另一范围的意见保持已汇总。
                plan_scope.raise_reconsideration(plan, entry, self._craft(entry))
                effects.append(dict(entry))
                effects.append(dict(plan))
        return effects

    def idempotent_scope(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> str:
        # 复议只认"意见+工艺"这一份回执：重复提交保持幂等；
        # 重新汇总属于新一轮评审，必须允许再次执行。
        if action == "发起复议":
            return f"{entry.get('id')}:{self._craft(entry)}"
        if action == "开始评审":
            # 复议后的重新评审属于新一轮，不能被上一轮的幂等窗口挡住。
            return f"status:{entry.get('status', '')}"
        if action == "汇总意见":
            plan = self._plan_for(entry)
            if plan is not None:
                plan_scope.ensure_scope(plan)
                rounds = sum(
                    1 for receipt in plan.get("复议回执清单", [])
                    if int(receipt.get("意见ID", 0)) == int(entry_id)
                )
                return (
                    f"round:{rounds}:{int(plan.get('审批批次', 0))}:"
                    f"{entry.get('status', '')}"
                )
        return ""

    def request_reconsideration(
        self, entry_id: int, craft: str = "", remark: str = ""
    ) -> tuple[dict[str, Any] | None, str]:
        """从评审清单发起复议：指向本条已汇总意见，并限定工艺范围。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if craft:
            entry["工艺范围"] = craft
        if remark:
            entry["复议说明"] = remark
        return self.run_action(entry_id, "发起复议")

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        before = dict(entry) if entry else None
        if action == "发起复议" and before is not None:
            plan = self._plan_for(before)
            existing = plan_scope.find_receipt(
                plan, int(before.get("id", 0)), self._craft(before)
            ) if plan else None
            if existing:
                # 重复提交复用同一份回执，不重复改状态、不新增待审项。
                return entry, (
                    f"复议已受理：回执{existing['回执编号']}指向意见#{existing.get('意见ID')}"
                    f"（{existing.get('专家')}·{existing.get('工艺')}）"
                )
        updated, message = super().run_action(entry_id, action)
        if updated is None or action != "发起复议" or before is None:
            return updated, message
        plan = self._plan_for(before)
        receipt = plan_scope.find_receipt(
            plan, int(before.get("id", 0)), self._craft(before)
        ) if plan else None
        if receipt:
            return updated, (
                f"复议已受理：回执{receipt['回执编号']}指向意见#{receipt.get('意见ID')}"
                f"（{receipt.get('专家')}·{receipt.get('工艺')}）"
            )
        return updated, message

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        base["pending_reviews"] = [
            {"方案": r.get("评审方案"), "专家": r.get("专家姓名"), "领域": r.get("专业领域")}
            for r in store.rows(self.MODULE) if r.get("status") in ("待评审", "评审中")
        ]
        base["reconsiderations"] = [
            {
                "意见ID": r.get("id"),
                "方案": r.get("评审方案"),
                "专家": r.get("专家姓名"),
                "工艺": plan_scope.review_craft(r),
                "回执": r.get("复议回执", ""),
            }
            for r in store.rows(self.MODULE) if r.get("status") == "需复议"
        ]
        return base

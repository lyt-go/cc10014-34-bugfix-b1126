"""修缮方案领域服务：基于勘查记录编制方案，已通过方案作为材料核验的工艺基准。

方案审批按工艺逐项结算：被专家复议覆盖的工艺进入待审并等待重新审核，
其余工艺的批准依据继续下发给现场，审批人能看到本次批准留下了哪些依据。
"""
from __future__ import annotations

import copy
from typing import Any

from app.services.base import BaseModuleService
from app.services import plan_scope
from app.store import store


class RestorationPlanService(BaseModuleService):
    MODULE = "restoration_plan"
    ENTITY = "修缮方案"
    OPERATION_TERM = "提交审核"
    LIST_FIELDS = ["方案编号", "对应勘查", "修缮工艺", "材料清单", "工期预估", "编制人", "方案版本", "备注说明"]
    REQUIRED_FIELDS = ["方案编号", "对应勘查", "修缮工艺"]
    STATUS_ORDER = ["编制中", "待审核", "已通过", "已驳回"]
    ACTION_RULES = {"提交审核": "待审核", "审核通过": "已通过", "驳回方案": "已驳回"}
    NEGATIVE_ACTIONS = ["驳回方案"]

    def idempotent_scope(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> str:
        # 同一审批批次内重复提交保持幂等；复议后重新审批属于新批次。
        if action == "审核通过":
            plan_scope.ensure_scope(entry)
            return f"batch:{int(entry.get('审批批次', 0))}"
        return ""

    def _reviews(self, entry_id: int) -> list[dict[str, Any]]:
        return [
            row for row in store.rows("expert_review")
            if str(row.get("评审方案", "")) == str(entry_id)
        ]

    def cross_module_verify(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> tuple[bool, str]:
        if action == "提交审核":
            # 关联勘查必须是"已提交"或"已复核"
            survey_id = entry.get("对应勘查", "")
            if survey_id:
                survey = store.find("building_survey", int(survey_id)) if survey_id.isdigit() else None
                if survey and survey.get("status") not in ("已提交", "已复核"):
                    return False, f"关联勘查{survey_id}状态为「{survey.get('status', '')}」，需先提交勘查记录"
        if action == "审核通过":
            if entry.get("status") not in ("待审核", "部分通过"):
                return False, f"方案当前状态「{entry.get('status')}」，不能重复审核"
            if entry.get("status") == "部分通过" and not any(
                item.get("状态") == "已复审，待审批"
                for item in plan_scope.ensure_scope_return(entry)
            ):
                return False, "复议工艺尚未重新汇总，不能重复审核本次批准"
            # 复议不阻断审批人：只把受影响工艺留在待审，其他工艺正常批准。
            reviews = self._reviews(entry_id)
            ungathered = [
                r for r in reviews
                if r.get("status") not in ("已汇总", "已通过", "需复议")
                and not plan_scope.find_receipt(
                    entry, int(r.get("id", 0)), plan_scope.review_craft(r))
            ]
            if ungathered:
                return False, "存在未完成的专家评审，无法审核通过"
            plan_scope.ensure_scope(entry)
            if reviews and not any(
                r.get("status") in ("已汇总", "已通过") for r in reviews
            ):
                return False, "所有专家意见都在复议中，没有可批准的工艺依据，请等待重新审核"
        return True, ""

    def cross_module_effect(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> list[dict]:
        effects = []
        if action == "审核通过":
            reviews = self._reviews(entry_id)
            outcome = plan_scope.apply_approval(
                entry, reviews, source="方案审核", approver=entry.get("审批人", "")
            )
            entry["status"] = "部分通过" if outcome["待审清单"] else "已通过"
            entry["pending"] = bool(outcome["待审清单"])
            entry["abnormal"] = False
            effects.append(dict(entry))
            # 本轮审批下发给现场的工艺依据（仅含仍然有效的工艺）。
            for basis in outcome["有效工艺依据"]:
                effects.append({
                    "类型": "有效工艺依据",
                    "方案ID": entry_id,
                    "工艺": basis.get("工艺"),
                    "意见ID": basis.get("意见ID"),
                    "专家": basis.get("专家"),
                    "审批批次": outcome["审批批次"],
                })
        elif action == "驳回方案":
            # 驳回后标记关联专家评审可复议
            reviews = self._reviews(entry_id)
            for review in reviews:
                if review.get("status") in ("评审中", "已汇总"):
                    review["status"] = "需复议"
                    review["pending"] = True
                    effects.append(dict(review))
        return effects

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        updated, message = super().run_action(entry_id, action)
        if updated is None or action != "审核通过":
            return updated, message
        note = updated.get("批准说明", "")
        return updated, f"{self.ENTITY}已审核通过" + (f"；{note}" if note else "")

    # ── 审批前查询：本次批准会留下哪些有效工艺、哪些仍在复议 ──
    def approval_preview(self, entry_id: int) -> dict[str, Any] | None:
        plan = store.find(self.MODULE, entry_id)
        if plan is None:
            return None
        plan_scope.ensure_scope(plan)
        return plan_scope.scope_summary(plan)

    def reconsideration_scope(self, entry_id: int) -> dict[str, Any] | None:
        """评审清单与方案审批共用的复议范围视图。"""
        plan = store.find(self.MODULE, entry_id)
        if plan is None:
            return None
        return plan_scope.scope_summary(plan)

    def craft_clearance(self, entry_id: int, craft: str) -> dict[str, Any] | None:
        """现场按工艺查凭据：有效、待重新审核或未覆盖。"""
        plan = store.find(self.MODULE, entry_id)
        if plan is None:
            return None
        return plan_scope.clearance(plan, craft)

    def issue_workfront(
        self, entry_id: int, craft: str, recipient: str = "", note: str = ""
    ) -> tuple[dict[str, Any] | None, str]:
        """施工方领取作业面：只接受当时仍然有效的工艺凭据。"""
        plan = store.find(self.MODULE, entry_id)
        if plan is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        plan_scope.ensure_scope(plan)
        scope = plan_scope.clearance(plan, craft)
        if scope["state"] == "待重新审核":
            receipt = (scope.get("pending_review") or {}).get("复议回执", "")
            return None, (
                f"工艺「{scope['craft']}」因复议{receipt}待重新审核，受理交接需等待复审结果"
            )
        if not scope["approved"]:
            return None, f"工艺「{scope['craft']}」当前没有有效审批依据，不能领取作业面"
        basis = scope["basis"] or {}
        if int(basis.get("审批批次") or 0) < int(plan.get("审批批次") or 0):
            return None, f"工艺「{scope['craft']}」的审批依据不是本次批准结果，需按本次审批重新领取"
        record = {
            "id": max(
                (int(item.get("id", 0)) for item in plan["作业面记录"]), default=0
            ) + 1,
            "作业面": f"{plan.get('方案编号', '')}-{scope['craft']}",
            "方案ID": plan.get("id"),
            "工艺": scope["craft"],
            "领取人": recipient,
            "领取时间": plan_scope.datetime.now().isoformat(timespec="seconds"),
            "审批批次": basis.get("审批批次"),
            "依据意见ID": basis.get("意见ID"),
            "依据专家": basis.get("专家"),
            "依据快照": copy.deepcopy(basis),
            "状态": "已受理",
            "备注": note,
        }
        plan["作业面记录"].append(record)
        return dict(record), (
            f"已按审批批次{basis.get('审批批次')}的{scope['craft']}依据"
            f"（意见#{basis.get('意见ID')}·{basis.get('专家')}）发放作业面"
        )

    def complete_workfront(
        self, entry_id: int, workfront_id: int | None = None,
        craft: str = "", recipient: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """完成已受理的作业面交接。

        复议不会追溯撤销复议前已经受理的交接：只要领取时使用的凭据真实有效，
        这条交接仍可完成；复议之后才来领取的工艺必须等待重新审核。
        """
        plan = store.find(self.MODULE, entry_id)
        if plan is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        plan_scope.ensure_scope(plan)
        target_craft = plan_scope.canonical_craft(craft)
        candidates = [
            record for record in plan.get("作业面记录", [])
            if record.get("状态") == "已受理"
        ]
        if workfront_id is not None:
            candidates = [
                record for record in candidates if int(record.get("id", 0)) == workfront_id
            ]
        else:
            if target_craft:
                candidates = [
                    record for record in candidates
                    if record.get("工艺") == target_craft
                ]
            if recipient:
                candidates = [
                    record for record in candidates if record.get("领取人") == recipient
                ]
        if not candidates:
            if target_craft:
                return None, (
                    f"工艺「{target_craft}」没有已受理的作业面交接；"
                    f"复议后需等重新审核通过再领取"
                )
            return None, "没有可完成的已受理作业面交接"
        record = candidates[-1]
        record["状态"] = "已交接"
        record["交接完成时间"] = plan_scope.datetime.now().isoformat(timespec="seconds")
        return dict(record), (
            f"作业面「{record.get('作业面')}」已按审批批次{record.get('审批批次')}的"
            f"凭据（意见#{record.get('依据意见ID')}·{record.get('依据专家')}）完成交接"
        )

    def _with_snapshot(self, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if entry is None:
            return None
        data = dict(entry)
        plan_scope.ensure_scope(data)
        data["复议范围"] = plan_scope.scope_summary(data)
        return data

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return self._with_snapshot(super().get_entry(entry_id))

    def list_entries(self, **kwargs: Any):
        items, total = super().list_entries(**kwargs)
        return [self._with_snapshot(item) for item in items], total

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        base["approved_plans"] = [
            {"id": r.get("id"), "工艺要求": r.get("方案编号"), "材料清单": r.get("材料清单")}
            for r in store.rows(self.MODULE) if r.get("status") == "已通过"
        ]
        base["partial_plans"] = [
            {
                "id": r.get("id"),
                "方案编号": r.get("方案编号"),
                "待审工艺": [item.get("工艺") for item in r.get("待审清单", [])],
                "有效工艺": [item.get("工艺") for item in r.get("有效工艺依据", [])],
            }
            for r in store.rows(self.MODULE) if r.get("status") == "部分通过"
        ]
        return base

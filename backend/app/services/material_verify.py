"""材料核验领域服务：核验材料时校验已通过方案中的工艺要求，签认后联动工序可用性。"""
from __future__ import annotations

from typing import Any

from app.services import plan_scope
from app.services.base import BaseModuleService
from app.store import store


class MaterialVerifyService(BaseModuleService):
    MODULE = "material_verify"
    ENTITY = "材料核验单"
    OPERATION_TERM = "开始核验"
    LIST_FIELDS = ["材料名称", "规格型号", "供应商", "送检批次", "检测报告", "核验人", "核验结果", "备注说明"]
    REQUIRED_FIELDS = ["材料名称", "规格型号", "供应商"]
    STATUS_ORDER = ["待核验", "核验中", "已签认", "已退回"]
    ACTION_RULES = {"开始核验": "核验中", "签认材料": "已签认", "退回材料": "已退回"}
    NEGATIVE_ACTIONS = []

    def cross_module_verify(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> tuple[bool, str]:
        if action == "签认材料":
            # 校验该材料是否在任一有效方案的工艺要求中出现；被复议的工艺
            # 只是暂时不能用，同一方案里其他仍然有效的工艺继续可用。
            plans = [
                row for row in store.rows("restoration_plan")
                if row.get("status") in ("已通过", "部分通过")
            ]
            if plans:
                material_name = entry.get("材料名称", "")
                spec = entry.get("规格型号", "")
                matched = False
                pending_hit = None
                mismatch_reasons = []
                for plan in plans:
                    craft_text = plan.get("修缮工艺", "")
                    if not (material_name in craft_text or (
                        spec and spec in plan.get("材料清单", "")
                    )):
                        mismatch_reasons.append(
                            f"方案{plan.get('方案编号','')}工艺要求: {craft_text}"
                        )
                        continue
                    matched = True
                    if plan.get("status") != "部分通过":
                        break
                    plan_scope.ensure_scope(plan)
                    # 材料名或其规格命中工艺的，只有该工艺在待审时才拦截。
                    pending = next(
                        (item for item in plan.get("待审清单", [])
                         if item.get("工艺") and (
                             item["工艺"] in material_name
                             or any(
                                 alias in material_name
                                 for alias in plan_scope.CRAFT_ALIASES.get(
                                     item["工艺"], (item["工艺"],))
                             )
                         )), None
                    )
                    if pending:
                        pending_hit = (plan, pending)
                        matched = False
                        continue
                    break
                if pending_hit:
                    plan, pending = pending_hit
                    return False, (
                        f"材料「{material_name}」对应的{pending.get('工艺')}工艺因复议"
                        f"{pending.get('复议回执')}待重新审核，暂不能签认；"
                        f"方案{plan.get('方案编号','')}其他工艺仍然有效"
                    )
                if not matched:
                    details = "; ".join(mismatch_reasons[:3])
                    return False, f"材料「{material_name}」未在任何已通过修缮方案的工艺中出现。{details}"
        return True, ""

    def cross_module_effect(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> list[dict]:
        effects = []
        if action == "签认材料":
            # 签认后，检查是否可以解锁需要此材料的工序
            for ws_row in store.rows("work_sequence"):
                if ws_row.get("status") == "待排期":
                    ws_row["需要材料已验证"] = True
                    effects.append(dict(ws_row))
        elif action == "退回材料":
            # 退回后标记关联工序材料未验证
            material_name = entry.get("材料名称", "")
            for ws_row in store.rows("work_sequence"):
                if ws_row.get("所需工匠", "") == material_name:
                    ws_row["abnormal"] = True
                    effects.append(dict(ws_row))
        return effects
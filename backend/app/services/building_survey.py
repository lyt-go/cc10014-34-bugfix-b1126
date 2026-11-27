"""建筑勘查领域服务：文保工程师对古建筑各部位勘查病害。勘查是修缮方案的前置输入。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class BuildingSurveyService(BaseModuleService):
    MODULE = "building_survey"
    ENTITY = "勘查记录"
    OPERATION_TERM = "开始勘查"
    LIST_FIELDS = ["建筑名称", "勘查部位", "病害类型", "残损等级", "测量数据", "影像编号", "勘查日期", "备注说明"]
    REQUIRED_FIELDS = ["建筑名称", "勘查部位", "病害类型"]
    STATUS_ORDER = ["待勘查", "勘查中", "已提交", "已复核"]
    ACTION_RULES = {"开始勘查": "勘查中", "提交记录": "已提交", "退回勘查": "待勘查"}
    NEGATIVE_ACTIONS = []

    def cross_module_verify(
        self, entry_id: int, action: str, entry: dict[str, Any]
    ) -> tuple[bool, str]:
        # 退回勘查时检查是否有关联的已通过方案，若有则阻止退回
        if action == "退回勘查":
            related_plans = [
                row for row in store.rows("restoration_plan")
                if row.get("对应勘查") == str(entry_id)
            ]
            if any(
                r.get("status") in ("已通过", "部分通过") for r in related_plans
            ):
                return False, "存在已通过的关联修缮方案，无法退回勘查"
        return True, ""

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        # 附加：已提交勘查列表（供方案模块参考）
        base["submitted"] = [
            dict(row) for row in store.rows(self.MODULE) if row.get("status") == "已提交"
        ]
        return base
"""专家复议范围测试：复议只重审受影响的工艺，石作等其他结论继续有效。"""
from __future__ import annotations

import pytest

from app.seed import SEED_ROWS
from app.services.building_survey import BuildingSurveyService
from app.services.expert_review import ExpertReviewService
from app.services.material_verify import MaterialVerifyService
from app.services.restoration_plan import RestorationPlanService
from app.store import store


@pytest.fixture(autouse=True)
def reset_store():
    store._idempotent_log.clear()
    store._resource_locks.clear()
    for name in list(store._tables.keys()):
        store._tables[name] = [dict(row) for row in SEED_ROWS.get(name, [])]
    yield


plan_service = RestorationPlanService()
expert_service = ExpertReviewService()


def plan_row(plan_id: int = 4) -> dict:
    return store.find("restoration_plan", plan_id)


def review_rows(plan_id: int = 4) -> list[dict]:
    return [r for r in store.rows("expert_review") if r["评审方案"] == str(plan_id)]


# ═══════════════════════════════════════════════════════════════════
# 测试1：C-37 复议后石作不被连带驳回
# ═══════════════════════════════════════════════════════════════════

def test_c37_reconsideration_only_hits_wood_scope():
    """甲对木作发起复议，乙已汇总的石作结论仍然是已汇总，方案不整案驳回"""
    stone_before = next(r for r in review_rows() if r["专家姓名"] == "乙")
    assert stone_before["status"] == "已汇总"

    updated, message = expert_service.run_action(4, "发起复议")
    assert updated is not None, message
    assert "RF-" in message

    reviews = {r["专家姓名"]: r for r in review_rows()}
    assert reviews["甲"]["status"] == "需复议"
    assert reviews["乙"]["status"] == "已汇总", "乙未被撤回的石作结论不得被复议误伤"
    assert reviews["乙"].get("复议回执") in (None, "")

    plan = plan_row()
    assert plan["status"] != "已驳回", "复议不应把整份方案驳回"
    assert plan["待审工艺"] == ["木作"]
    assert plan["待审清单"][0]["意见ID"] == reviews["甲"]["id"]


def test_c37_duplicate_reconsideration_single_receipt():
    """重复发起复议只产生一份回执，不新增待审项"""
    expert_service.run_action(4, "发起复议")
    first = plan_row()["复议回执清单"]
    assert len(first) == 1

    expert_service.run_action(4, "发起复议")
    plan = plan_row()
    assert len(plan["复议回执清单"]) == 1
    assert len(plan["待审清单"]) == 1
    receipt = plan["复议回执清单"][0]
    assert receipt["意见ID"] == 4
    assert receipt["工艺"] == "木作"


def test_reconsideration_requires_gathered_review():
    """复议必须指向已汇总意见，未完成的意见不能被复议"""
    pending_review, _ = expert_service.create_entry({
        "评审方案": "4", "专家姓名": "丁", "专业领域": "石作", "工艺范围": "石作",
    })
    expert_service.run_action(pending_review["id"], "开始评审")
    updated, message = expert_service.run_action(pending_review["id"], "发起复议")
    assert updated is None
    assert "已汇总" in message


def test_reconsideration_craft_must_be_in_plan_scope():
    """复议工艺必须落在方案声明的修缮工艺范围内"""
    review, _ = expert_service.create_entry({
        "评审方案": "4", "专家姓名": "丙", "专业领域": "彩绘", "工艺范围": "彩绘",
        "评审结论": "彩绘可行",
    })
    expert_service.run_action(review["id"], "开始评审")
    expert_service.run_action(review["id"], "汇总意见")
    updated, message = expert_service.run_action(review["id"], "发起复议")
    assert updated is None
    assert "工艺" in message


# ═══════════════════════════════════════════════════════════════════
# 测试2：审批在途与复议冲突时，审批人拿到本次批准的有效依据
# ═══════════════════════════════════════════════════════════════════

def test_approval_in_flight_reports_surviving_basis():
    """方案待审核时复议木作，审核通过后仍留下石作的有效依据"""
    assert plan_row()["status"] == "待审核"
    expert_service.run_action(4, "发起复议")

    preview = plan_service.approval_preview(4)
    assert preview["approval_in_flight"] is True
    assert preview["pending_crafts"] == ["木作"]
    assert [item["工艺"] for item in preview["approval_candidates"]] == ["石作"]
    assert "石作" in preview["message"] and "木作" in preview["message"]

    updated, message = plan_service.run_action(4, "审核通过")
    assert updated is not None, message
    plan = plan_row()
    assert plan["status"] == "部分通过"
    assert [basis["工艺"] for basis in plan["本次批准有效工艺依据"]] == ["石作"]
    assert plan["本次批准有效工艺依据"][0]["意见ID"] == 5
    assert [item["工艺"] for item in plan["待审清单"]] == ["木作"]
    assert "石作(意见#5·乙)" in message and "木作(意见#4，回执RF-0001)" in message


def test_reconsideration_tracked_to_source_review():
    """木作被重审必须能追到导致重审的意见和回执"""
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")
    plan = plan_row()

    pending = plan["待审清单"][0]
    assert pending["意见ID"] == 4
    assert pending["专家"] == "甲"
    assert pending["复议回执"] == plan["复议回执清单"][0]["回执编号"]
    reviewed = store.find("expert_review", 4)
    assert reviewed["被复议工艺"] == "木作"
    assert reviewed["复议回执"] == pending["复议回执"]

    history = plan["历史工艺依据"]
    if history:
        assert all(basis["复议回执"] == pending["复议回执"] for basis in history)


def test_review_board_and_approval_share_scope():
    """评审清单与方案审批的复议范围一致"""
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")

    scope = plan_service.reconsideration_scope(4)
    board = scope["review_board"]
    states = {item["专家"]: item["范围状态"] for item in board["items"]}
    assert states["甲"] == "复议待审"
    assert states["乙"] == "结论有效"
    assert scope["pending_crafts"] == ["木作"]
    assert scope["valid_crafts"] == ["石作"]

    preview = plan_service.approval_preview(4)
    assert preview["pending_crafts"] == scope["pending_crafts"]
    assert preview["review_board"]["items"] == board["items"]


# ═══════════════════════════════════════════════════════════════════
# 测试3：施工方按审批领取作业面
# ═══════════════════════════════════════════════════════════════════

def test_workfront_follows_actual_approval():
    """石作可按本次审批领作业面；木作必须等重新审核"""
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")

    wood, wood_msg = plan_service.issue_workfront(4, "木作", "施工方-李")
    assert wood is None and "待重新审核" in wood_msg

    stone, stone_msg = plan_service.issue_workfront(4, "石作", "施工方-李")
    assert stone is not None, stone_msg
    assert stone["审批批次"] == plan_row()["审批批次"]
    assert stone["依据意见ID"] == 5
    assert stone["依据专家"] == "乙"
    assert stone["状态"] == "已受理"

    done, done_msg = plan_service.complete_workfront(4, stone["id"])
    assert done is not None, done_msg
    assert done["状态"] == "已交接"


def test_approval_in_flight_waits_for_retrial():
    """复议已进入重新评审但未汇总时，审批人不能先把木作当作有效依据批准掉"""
    expert_service.run_action(4, "发起复议")
    expert_service.run_action(4, "开始评审")

    preview = plan_service.approval_preview(4)
    assert preview["pending_crafts"] == ["木作"]
    assert [item["工艺"] for item in preview["approval_candidates"]] == ["石作"]

    updated, message = plan_service.run_action(4, "审核通过")
    assert updated is not None, message
    plan = plan_row()
    assert [basis["工艺"] for basis in plan["本次批准有效工艺依据"]] == ["石作"]
    assert [item["工艺"] for item in plan["待审清单"]] == ["木作"]


def test_partial_plan_cannot_approve_before_retrial():
    """部分通过后复议工艺尚未重新汇总，不能重复审核出第二份批准"""
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")
    batch = plan_row()["审批批次"]

    updated, message = plan_service.run_action(4, "审核通过")
    assert updated is None
    assert "复议" in message
    assert plan_row()["审批批次"] == batch


def test_workfront_after_reconsideration_completes():
    """复议后重新审核通过，木作可领作业面并完成交接"""
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")
    # 等待状态：现场不能按旧凭据领取
    assert plan_service.issue_workfront(4, "木作", "施工方-李")[0] is None

    expert_service.run_action(4, "开始评审")
    expert_service.run_action(4, "汇总意见")
    updated, message = plan_service.run_action(4, "审核通过")
    assert updated is not None, message
    plan = plan_row()
    assert plan["status"] == "已通过"
    assert {basis["工艺"] for basis in plan["有效工艺依据"]} == {"木作", "石作"}
    assert plan["待审清单"] == []

    wood, wood_msg = plan_service.issue_workfront(4, "木作", "施工方-李")
    assert wood is not None, wood_msg
    assert wood["依据意见ID"] == 4
    assert wood["审批批次"] == plan["审批批次"]
    done, _ = plan_service.complete_workfront(4, wood["id"])
    assert done is not None and done["状态"] == "已交接"


def test_previously_accepted_workfront_survives_reconsideration():
    """复议前已受理的交接不因复议被追溯撤销"""
    plan_service.run_action(4, "审核通过")
    stone, message = plan_service.issue_workfront(4, "石作", "施工方-李")
    assert stone is not None, message

    expert_service.run_action(4, "发起复议")
    done, done_msg = plan_service.complete_workfront(4, stone["id"])
    assert done is not None, done_msg
    assert done["状态"] == "已交接"
    assert done["依据意见ID"] == 5


def test_material_sign_respects_pending_craft():
    """石作材料仍可签认，木作材料因复议待审而暂缓"""
    material_service = MaterialVerifyService()
    expert_service.run_action(4, "发起复议")
    plan_service.run_action(4, "审核通过")

    stone, _ = material_service.create_entry({
        "材料名称": "石构件", "规格型号": "600x400x200", "供应商": "石料厂",
    })
    updated, message = material_service.run_action(stone["id"], "签认材料")
    assert updated is not None, f"石作仍有效，材料应可签认: {message}"

    wood, _ = material_service.create_entry({
        "材料名称": "木梁", "规格型号": "φ200", "供应商": "木料厂",
    })
    blocked, blocked_msg = material_service.run_action(wood["id"], "签认材料")
    assert blocked is None
    assert "待重新审核" in blocked_msg


# ═══════════════════════════════════════════════════════════════════
# 测试4：兼容已有审批入口
# ═══════════════════════════════════════════════════════════════════

def test_legacy_single_craft_summary_still_approves_plan():
    """原有单工艺方案：汇总意见仍自动推动方案通过"""
    survey_service = BuildingSurveyService()
    survey, _ = survey_service.create_entry({
        "建筑名称": "偏殿", "勘查部位": "屋面", "病害类型": "漏雨",
    })
    survey_service.run_action(survey["id"], "开始勘查")
    survey_service.run_action(survey["id"], "提交记录")
    plan, _ = plan_service.create_entry({
        "方案编号": "LEGACY-001", "对应勘查": str(survey["id"]),
        "修缮工艺": "瓦作：揭瓦重铺",
    })
    plan_service.run_action(plan["id"], "提交审核")
    review, _ = expert_service.create_entry({
        "评审方案": str(plan["id"]), "专家姓名": "王教授", "专业领域": "瓦作",
    })
    expert_service.run_action(review["id"], "开始评审")
    updated, message = expert_service.run_action(review["id"], "汇总意见")
    assert updated is not None, message
    assert plan_row(plan["id"])["status"] == "已通过"


def test_legacy_plan_still_can_be_rejected():
    """原本的驳回入口保持可用"""
    plan = plan_row()
    updated, message = plan_service.run_action(
        next(r["id"] for r in store.rows("restoration_plan")
             if r["status"] == "待审核" and r["id"] != 4),
        "驳回方案",
    )
    assert updated is not None, message
    assert updated["status"] == "已驳回"
    assert plan["status"] == "待审核"

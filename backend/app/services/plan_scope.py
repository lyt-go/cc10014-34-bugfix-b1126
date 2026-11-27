"""修缮方案与专家评审共享的工艺范围工具。

专家复议只影响被指到的那一条已汇总意见及其工艺范围；方案审批要把
"本次批准仍然有效"的工艺依据和"待重新审核"的工艺范围同时讲清楚。
两个入口都从这里取范围，避免评审清单和方案审批各算一套。
"""
from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from app.store import store

# 专业领域/工艺名称的口语别名，用于把方案里的工艺文本和专家意见的领域对齐。
CRAFT_ALIASES: dict[str, tuple[str, ...]] = {
    "木作": ("木作", "木结构", "大木", "木构件", "木梁", "木柱", "木雕", "木料"),
    "石作": ("石作", "石构件", "石雕", "石材", "石碑", "石栏", "台基"),
    "瓦作": ("瓦作", "瓦面", "屋面", "青瓦", "琉璃瓦"),
    "彩绘": ("彩绘", "油饰", "壁画", "彩画"),
    "土作": ("土作", "夯土", "地基"),
}

RECEIPT_PREFIX = "RF-"


def canonical_craft(value: Any) -> str:
    """把工艺/专业领域的写法收敛成可比较的工艺名。"""
    text = str(value or "").strip()
    if not text:
        return ""
    for craft, aliases in CRAFT_ALIASES.items():
        if any(alias in text for alias in aliases):
            return craft
    return text


def plan_crafts(plan: dict[str, Any]) -> list[str]:
    """读取方案声明的工艺范围，保留稳定顺序。"""
    raw = str(plan.get("修缮工艺") or "")
    found = [
        craft
        for craft, aliases in CRAFT_ALIASES.items()
        if any(alias in raw for alias in aliases)
    ]
    if found:
        return found
    tokens = [
        canonical_craft(part)
        for part in re.split(r"[、,，/;；+＋\s]+", raw)
        if part.strip()
    ]
    return list(dict.fromkeys(token for token in tokens if token))


def review_craft(review: dict[str, Any]) -> str:
    return canonical_craft(review.get("工艺范围") or review.get("专业领域"))


def craft_covered(plan: dict[str, Any], craft: str) -> bool:
    """该工艺是否属于方案声明的范围。"""
    craft = canonical_craft(craft)
    if not craft:
        return False
    if craft in plan_crafts(plan):
        return True
    raw = str(plan.get("修缮工艺") or "")
    if craft in raw:
        return True
    return any(alias in raw for alias in CRAFT_ALIASES.get(craft, ()))


def ensure_scope(plan: dict[str, Any]) -> None:
    """补齐方案上的范围字段，兼容升级前已存在的方案记录。"""
    plan.setdefault("待审清单", [])
    plan.setdefault("有效工艺依据", [])
    plan.setdefault("历史工艺依据", [])
    plan.setdefault("复议回执清单", [])
    plan.setdefault("待审工艺", [])
    plan.setdefault("工艺审批状态", {})
    plan.setdefault("审批批次", 0)
    plan.setdefault("审批记录", [])
    plan.setdefault("本次批准有效工艺依据", [])
    plan.setdefault("作业面记录", [])


def ensure_scope_return(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """补齐范围字段并返回待审清单，供动作前置校验使用。"""
    ensure_scope(plan)
    return plan.get("待审清单", [])


def active_bases(plan: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_scope(plan)
    return [
        basis
        for basis in plan.get("有效工艺依据", [])
        if basis.get("状态", "有效") == "有效"
    ]


def find_receipt(
    plan: dict[str, Any], review_id: int, craft: str | None = None
) -> dict[str, Any] | None:
    ensure_scope(plan)
    for receipt in plan.get("复议回执清单", []):
        if int(receipt.get("意见ID", 0)) != int(review_id):
            continue
        if craft is not None and receipt.get("工艺") != canonical_craft(craft):
            continue
        return receipt
    return None


def next_receipt_no() -> str:
    """复议回执全局顺序号；重复提交复用已有回执，不再分配新号。"""
    highest = 0
    for plan in store.rows("restoration_plan"):
        for receipt in plan.get("复议回执清单", []) or []:
            text = str(receipt.get("回执编号", ""))
            if text.startswith(RECEIPT_PREFIX) and text[len(RECEIPT_PREFIX):].isdigit():
                highest = max(highest, int(text[len(RECEIPT_PREFIX):]))
    return f"{RECEIPT_PREFIX}{highest + 1:04d}"


def create_receipt(
    plan: dict[str, Any], review: dict[str, Any], craft: str
) -> dict[str, Any]:
    """为一条已汇总意见创建唯一的复议回执，并返回它。"""
    ensure_scope(plan)
    existing = find_receipt(plan, int(review["id"]), craft)
    if existing:
        return existing
    receipt = {
        "回执编号": next_receipt_no(),
        "方案ID": plan.get("id"),
        "方案编号": plan.get("方案编号", ""),
        "意见ID": review.get("id"),
        "专家": review.get("专家姓名", ""),
        "专业领域": review.get("专业领域", ""),
        "工艺": canonical_craft(craft),
        "评审结论": review.get("评审结论", ""),
        "修改建议": review.get("修改建议", ""),
        "发起时间": datetime.now().isoformat(timespec="seconds"),
        "状态": "已受理",
    }
    plan["复议回执清单"].append(receipt)
    return receipt


def mark_reconsideration(
    plan: dict[str, Any], review: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    """只把被复议意见覆盖的工艺移入待审，其他工艺依据原样保留。"""
    ensure_scope(plan)
    craft = review_craft(review)
    # 当前有效依据中，属于该工艺的转入历史并标记复议；其他工艺一条不动。
    remaining: list[dict[str, Any]] = []
    for basis in plan.get("有效工艺依据", []):
        if basis.get("工艺") == craft:
            archived = copy.deepcopy(basis)
            archived["状态"] = "复议待审"
            archived["复议回执"] = receipt["回执编号"]
            plan["历史工艺依据"].append(archived)
        else:
            remaining.append(basis)
    plan["有效工艺依据"] = remaining

    # 同一条意见/工艺只保留一份待审项。
    pending = [
        item
        for item in plan.get("待审清单", [])
        if not (
            int(item.get("意见ID", 0)) == int(review["id"])
            and item.get("工艺") == craft
        )
    ]
    pending.append({
        "工艺": craft,
        "意见ID": review.get("id"),
        "专家": review.get("专家姓名", ""),
        "专业领域": review.get("专业领域", ""),
        "状态": "需复议",
        "复议回执": receipt["回执编号"],
        "原结论": review.get("评审结论", ""),
        "修改建议": review.get("修改建议", ""),
        "发起时间": receipt["发起时间"],
    })
    plan["待审清单"] = pending
    plan["待审工艺"] = [item.get("工艺") for item in pending]
    plan.setdefault("工艺审批状态", {})[craft] = "待复审"

    # 审批在途时保持待审核；已经批准过的方案退成部分通过，绝不整案驳回。
    if plan.get("status") in ("已通过", "部分通过"):
        plan["status"] = "部分通过"
    plan["pending"] = True
    plan["abnormal"] = True
    return receipt


def raise_reconsideration(
    plan: dict[str, Any], review: dict[str, Any], craft: str | None = None
) -> dict[str, Any]:
    """登记一次复议：指向具体已汇总意见，只改这道工艺的范围。

    同一条意见+工艺重复提交复用同一份回执，不会产生第二份。
    """
    ensure_scope(plan)
    craft = canonical_craft(craft or review_craft(review))
    receipt = create_receipt(plan, review, craft)
    review["status"] = "需复议"
    review["pending"] = True
    review["abnormal"] = True
    review["复议回执"] = receipt["回执编号"]
    review["被复议工艺"] = craft
    mark_reconsideration(plan, review, receipt)
    return receipt


def finalize_reconsideration(
    plan: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any] | None:
    """复议意见重新汇总后保留追溯信息，等待方案重新批准。"""
    ensure_scope(plan)
    craft = review_craft(review)
    receipt = find_receipt(plan, int(review["id"]), craft)
    if receipt:
        receipt["状态"] = "已复审"
    changed = False
    for item in plan.get("待审清单", []):
        if int(item.get("意见ID", 0)) == int(review["id"]) and item.get("工艺") == craft:
            item["状态"] = "已复审，待审批"
            changed = True
    return receipt if changed else None


def extend_approval(
    plan: dict[str, Any], review: dict[str, Any], source: str = "专家补充汇总"
) -> dict[str, Any] | None:
    """方案已批准后新汇总的意见：只追加本工艺的有效依据，不动其他工艺。"""
    ensure_scope(plan)
    craft = review_craft(review)
    if not craft:
        return None
    if any(
        int(item.get("意见ID", 0)) == int(review.get("id", 0))
        and item.get("工艺") == craft
        for item in plan.get("待审清单", [])
    ):
        return None
    basis = {
        "工艺": craft,
        "意见ID": review.get("id"),
        "专家": review.get("专家姓名", ""),
        "专业领域": review.get("专业领域", ""),
        "结论": review.get("评审结论", ""),
        "修改建议": review.get("修改建议", ""),
        "审批批次": plan.get("审批批次", 0),
        "审批来源": source,
        "状态": "有效",
    }
    remaining = [
        item for item in active_bases(plan)
        if not (
            item.get("工艺") == craft
            or int(item.get("意见ID", 0)) == int(review.get("id", 0))
        )
    ]
    remaining.append(basis)
    plan["有效工艺依据"] = remaining
    plan.setdefault("工艺审批状态", {})[craft] = "已通过"
    if plan.get("status") == "部分通过" and not plan.get("待审清单"):
        plan["status"] = "已通过"
        plan["pending"] = False
    return basis


def _decision_note(plan: dict[str, Any], valid: list[dict[str, Any]],
                   pending: list[dict[str, Any]]) -> str:
    valid_text = "、".join(
        f"{item.get('工艺')}(意见#{item.get('意见ID')}·{item.get('专家')})"
        for item in valid
    ) or "无"
    pending_text = "、".join(
        f"{item.get('工艺')}(意见#{item.get('意见ID')}，回执{item.get('复议回执')})"
        for item in pending
    ) or "无"
    return f"本次批准仍有效的工艺依据：{valid_text}；待重新审核：{pending_text}"


def apply_approval(
    plan: dict[str, Any],
    reviews: list[dict[str, Any]],
    *,
    source: str = "方案审核",
    approver: str = "",
) -> dict[str, Any]:
    """按当前意见结算一次方案批准，生成不可变的本次批准依据快照。"""
    ensure_scope(plan)
    batch = int(plan.get("审批批次", 0)) + 1
    valid_reviews = [r for r in reviews if r.get("status") in ("已汇总", "已通过")]
    # 需复议、以及复议后重新评审还没汇总的意见，都属于本次不能批准的工艺范围。
    pending_reviews = [
        r for r in reviews
        if r.get("status") == "需复议"
        or (
            r.get("status") not in ("已汇总", "已通过")
            and find_receipt(plan, int(r.get("id", 0)), review_craft(r))
        )
    ]
    valid_crafts = _reviewed_crafts(plan.get("id"), valid_reviews)
    pending_crafts = _reviewed_crafts(plan.get("id"), pending_reviews)

    new_bases: list[dict[str, Any]] = []
    for review in valid_reviews:
        craft = review_craft(review)
        if not craft or craft in pending_crafts:
            continue
        new_bases.append({
            "工艺": craft,
            "意见ID": review.get("id"),
            "专家": review.get("专家姓名", ""),
            "专业领域": review.get("专业领域", ""),
            "结论": review.get("评审结论", ""),
            "修改建议": review.get("修改建议", ""),
            "审批批次": batch,
            "审批来源": source,
            "状态": "有效",
        })
    # 没有对应专家意见、但此前已经有效的工艺依据保留下来。
    covered = valid_crafts | pending_crafts
    seen = {basis.get("工艺") for basis in new_bases}
    for basis in active_bases(plan):
        craft = basis.get("工艺")
        if craft not in covered and craft not in seen:
            new_bases.append(copy.deepcopy(basis))
            seen.add(craft)

    # 被复议覆盖的旧依据转入历史，绝不继续作为现场凭据。
    for basis in active_bases(plan):
        if basis.get("工艺") in pending_crafts:
            archived = copy.deepcopy(basis)
            archived["状态"] = "复议待审"
            receipt = find_receipt(
                plan, int(archived.get("意见ID", 0)), archived.get("工艺"))
            if receipt:
                archived["复议回执"] = receipt.get("回执编号")
            plan["历史工艺依据"].append(archived)
    plan["有效工艺依据"] = new_bases

    old_pending = {
        (int(item.get("意见ID", 0)), item.get("工艺")): item
        for item in plan.get("待审清单", [])
    }
    pending_items: list[dict[str, Any]] = []
    for review in pending_reviews:
        craft = review_craft(review)
        key = (int(review.get("id", 0)), craft)
        item = old_pending.get(key, {})
        pending_items.append({
            "工艺": craft,
            "意见ID": review.get("id"),
            "专家": review.get("专家姓名", ""),
            "专业领域": review.get("专业领域", ""),
            "状态": "需复议",
            "复议回执": item.get("复议回执") or (
                find_receipt(plan, int(review.get("id", 0)), craft) or {}
            ).get("回执编号", ""),
            "原结论": review.get("评审结论", ""),
            "发起时间": item.get("发起时间", ""),
        })
    plan["待审清单"] = pending_items
    plan["待审工艺"] = [item.get("工艺") for item in pending_items]

    states = {basis.get("工艺"): "已通过" for basis in new_bases}
    for item in pending_items:
        states[item.get("工艺")] = "待复审"
    plan["工艺审批状态"] = states
    plan["审批批次"] = batch
    snapshot = copy.deepcopy(new_bases)
    plan["本次批准有效工艺依据"] = snapshot
    note = _decision_note(plan, snapshot, pending_items)
    plan["批准说明"] = note
    plan["审批记录"].append({
        "审批批次": batch,
        "审批来源": source,
        "审批人": approver,
        "审批时间": datetime.now().isoformat(timespec="seconds"),
        "有效工艺": [basis.get("工艺") for basis in snapshot],
        "待审工艺": [item.get("工艺") for item in pending_items],
        "说明": note,
    })
    return {
        "审批批次": batch,
        "有效工艺依据": snapshot,
        "待审清单": copy.deepcopy(pending_items),
        "说明": note,
    }


def _reviewed_crafts(plan_id: Any, reviews: list[dict[str, Any]]) -> set[str]:
    return {review_craft(review) for review in reviews if review_craft(review)}


def review_board(plan: dict[str, Any]) -> dict[str, Any]:
    """评审清单视图：每条意见的工艺范围、是否被复议、指向的回执。

    与方案审批的复议范围同源，避免一处显示已驳回、另一处还在批准。
    """
    ensure_scope(plan)
    reviews = [
        row for row in store.rows("expert_review")
        if str(row.get("评审方案", "")) == str(plan.get("id"))
    ]
    pending = {
        int(item.get("意见ID", 0)): item for item in plan.get("待审清单", [])
    }
    items = []
    for review in reviews:
        craft = review_craft(review)
        pending_item = pending.get(int(review.get("id", 0)))
        if pending_item:
            state = "复议待审"
        elif review.get("status") in ("已汇总", "已通过"):
            state = "结论有效"
        else:
            state = "评审进行中"
        items.append({
            "意见ID": review.get("id"),
            "专家": review.get("专家姓名", ""),
            "专业领域": review.get("专业领域", ""),
            "工艺": craft,
            "评审结论": review.get("评审结论", ""),
            "评审状态": review.get("status", ""),
            "范围状态": state,
            "复议回执": (pending_item or {}).get("复议回执", ""),
            "依据仍有效": state == "结论有效",
        })
    return {
        "plan_id": plan.get("id"),
        "方案编号": plan.get("方案编号", ""),
        "plan_status": plan.get("status", ""),
        "items": items,
        "pending_crafts": [item.get("工艺") for item in plan.get("待审清单", [])],
        "valid_crafts": [basis.get("工艺") for basis in active_bases(plan)],
        "receipts": copy.deepcopy(plan.get("复议回执清单", [])),
    }


def scope_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """评审清单与方案审批共用的一套复议范围视图。"""
    ensure_scope(plan)
    reviews = [
        row for row in store.rows("expert_review")
        if str(row.get("评审方案", "")) == str(plan.get("id"))
    ]
    pending = [
        {
            "工艺": item.get("工艺"),
            "意见ID": item.get("意见ID"),
            "专家": item.get("专家"),
            "状态": item.get("状态", "需复议"),
            "复议回执": item.get("复议回执", ""),
            "原结论": item.get("原结论", ""),
        }
        for item in plan.get("待审清单", [])
    ]
    valid = [
        {
            "工艺": basis.get("工艺"),
            "意见ID": basis.get("意见ID"),
            "专家": basis.get("专家"),
            "结论": basis.get("结论", ""),
            "审批批次": basis.get("审批批次"),
            "状态": basis.get("状态", "有效"),
        }
        for basis in active_bases(plan)
    ]
    pending_ids = {int(item.get("意见ID", 0)) for item in pending}
    candidates = []
    for review in reviews:
        if review.get("status") != "已汇总":
            continue
        craft = review_craft(review)
        if not craft or craft in {item.get("工艺") for item in pending}:
            continue
        candidates.append({
            "工艺": craft,
            "意见ID": review.get("id"),
            "专家": review.get("专家姓名", ""),
            "结论": review.get("评审结论", ""),
            "来源": "已汇总意见",
        })
    return {
        "plan_id": plan.get("id"),
        "方案编号": plan.get("方案编号", ""),
        "plan_status": plan.get("status", ""),
        "approval_in_flight": plan.get("status") == "待审核",
        "approval_batch": plan.get("审批批次", 0),
        "plan_crafts": plan_crafts(plan),
        "valid_bases": valid,
        "valid_crafts": [basis.get("工艺") for basis in valid],
        "pending_reviews": pending,
        "pending_crafts": [item.get("工艺") for item in pending],
        "approval_candidates": candidates,
        "receipts": copy.deepcopy(plan.get("复议回执清单", [])),
        "last_approval_bases": copy.deepcopy(plan.get("本次批准有效工艺依据", [])),
        "review_count": len(reviews),
        "review_ids": [review.get("id") for review in reviews],
        "covered_review_ids": sorted(pending_ids),
        "workfronts": copy.deepcopy(plan.get("作业面记录", [])),
        "review_board": review_board(plan),
        "message": _decision_note(plan, candidates, pending),
    }


def clearance(plan: dict[str, Any], craft: str) -> dict[str, Any]:
    """现场办理某工艺时，判断依据是否仍然有效或需等待复议。"""
    ensure_scope(plan)
    craft = canonical_craft(craft)
    basis = next(
        (item for item in active_bases(plan) if item.get("工艺") == craft), None
    )
    pending = next(
        (item for item in plan.get("待审清单", []) if item.get("工艺") == craft), None
    )
    covered = craft_covered(plan, craft)
    if pending:
        state = "待重新审核"
    elif basis:
        state = "有效"
    elif covered:
        state = "未批准"
    else:
        state = "未覆盖"
    return {
        "plan_id": plan.get("id"),
        "plan_status": plan.get("status", ""),
        "craft": craft,
        "covered": covered,
        "approved": basis is not None,
        "pending": pending is not None,
        "state": state,
        "basis": copy.deepcopy(basis) if basis else None,
        "pending_review": copy.deepcopy(pending) if pending else None,
        "approval_batch": plan.get("审批批次", 0),
        "valid_crafts": [item.get("工艺") for item in active_bases(plan)],
        "pending_crafts": [item.get("工艺") for item in plan.get("待审清单", [])],
    }

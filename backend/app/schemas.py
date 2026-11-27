"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None


class WorkfrontPayload(BaseModel):
    """施工方领取作业面：必须指明工艺和领取人。"""

    craft: str
    recipient: str = ""
    note: str | None = None


class WorkfrontCompletePayload(BaseModel):
    """完成作业面交接：可按交接单号，或按工艺+领取人定位已受理记录。"""

    workfront_id: int | None = None
    craft: str = ""
    recipient: str = ""


class ReconsiderationPayload(BaseModel):
    """发起复议：必须指向具体已汇总意见，并限定工艺范围。"""

    craft: str = ""
    remark: str | None = None

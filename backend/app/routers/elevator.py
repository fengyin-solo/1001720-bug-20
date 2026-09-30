"""电梯设备接口：维护电梯设备，覆盖办理投用、停用电梯等动作。

分页参数（page/size）与筛选条件（keyword/status）随请求一起下发，
偏移、总数、页码由后端一次算好并回传，前端只负责展示；
状态变更需携带操作单位 operatorUnit，归属不符由后端拒绝。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.elevator import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    STATUS_ORDER,
    ElevatorService,
)

router = APIRouter(prefix="/api/elevator", tags=["电梯设备"])

service = ElevatorService()

LIST_FIELDS = ["电梯编号", "电梯名称", "使用单位", "载重规格", "层站数量", "使用场所", "投用日期", "下次检验日", "电梯状态"]
STATUSES = STATUS_ORDER


def _page_params(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, description="每页条数"),
) -> tuple[int, int]:
    if size > MAX_PAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"每页最多 {MAX_PAGE_SIZE} 条，请缩小分页范围")
    return page, size


@router.get("/stats")
def stats() -> dict[str, int]:
    """电梯台数概览：统计未加筛选的全量列表结果，与列表默认范围、运营概览口径一致。"""
    return service.overview_stats()


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按电梯编号检索"),
    status: str | None = Query(default=None, description="待检、在用、停用"),
) -> dict[str, Any]:
    """导出电梯设备清单：条件随请求一起下发，返回当前筛选范围下的全量数据。"""
    items, total = service.list_all(keyword=keyword, status=status)
    return {"module": "elevator", "keyword": keyword, "status": status, "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按电梯编号检索"),
    status: str | None = Query(default=None, description="待检、在用、停用"),
    pagination: tuple[int, int] = Depends(_page_params),
) -> PageResult[dict]:
    """按电梯编号与状态过滤电梯设备列表；没有数据时返回空页，不报错。"""
    page, size = pagination
    items, total, page = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条电梯设备，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="电梯设备已登记，初始状态为待检", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    operatorUnit: str | None = Query(default=None, description="操作人所属使用单位，需与电梯归属一致"),
) -> ActionResult:
    """对单条电梯设备执行办理投用、停用电梯；跳档、回退、重复提交、跨单位都会被拦下并说明原因。"""
    values = payload.values or {}
    action = str(values.get("action") or "").strip()
    # 操作单位允许放在请求体或查询参数里，查询参数优先
    unit = operatorUnit or str(values.get("operatorUnit") or "").strip() or None
    entry, message, _changed = service.run_action(entry_id, action, operator_unit=unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条电梯设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"电梯设备 {entry_id} 不存在或已归档")
    return entry

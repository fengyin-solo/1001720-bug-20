"""电梯设备接口：维护电梯设备，覆盖办理投用、安排检修、停用电梯等动作。"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.elevator import DEFAULT_UNIT, ElevatorService

router = APIRouter(prefix="/api/elevator", tags=["电梯设备"])

service = ElevatorService()

LIST_FIELDS = ["电梯编号", "电梯名称", "载重规格", "层站数量", "使用单位", "使用场所", "投用日期", "下次检验日", "电梯状态"]
STATUSES = ["待投用", "正常运行", "停梯检修", "已停用"]
STAT_LABELS = {"全部": "电梯总数", "待投用": "待检电梯", "正常运行": "在用电梯", "停梯检修": "停梯检修", "已停用": "已停用"}


def _resolve_unit(payload: EntryPayload, x_use_unit: str | None) -> str:
    """处置单位随请求下发：优先请求体里的使用单位，其次请求头，缺省落到本单位。

    请求头按 HTTP 规范只能是 ASCII，中文单位名用百分号编码（encodeURIComponent）。
    """
    unit = str(payload.values.get("使用单位") or "").strip()
    if not unit and x_use_unit:
        unit = unquote(x_use_unit).strip()
    return unit or DEFAULT_UNIT


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按电梯编号检索"),
    status: str | None = Query(default=None, description="待投用、正常运行、停梯检修、已停用"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, description="每页条数"),
) -> PageResult[dict]:
    """筛选条件、页码、每页条数随请求下发；偏移、总数、页码、总页数由后端一次算好。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"设备状态「{status}」不在可筛选范围内")
    items, total, current, pages = service.list_entries(
        keyword=keyword, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=current, size=size, pages=pages)


@router.get("/stats")
def elevator_stats(
    keyword: str | None = Query(default=None, description="按电梯编号检索"),
    status: str | None = Query(default=None, description="与列表保持同一份筛选条件"),
) -> dict[str, Any]:
    """运营概览卡片：台数与列表取自同一份筛选结果。"""
    summary = service.summary(keyword=keyword, status=status)
    return {
        "module": "elevator",
        "total": summary["全部"],
        "cards": [
            {"label": STAT_LABELS[key], "status": key, "value": summary[key]}
            for key in ["全部", "待投用", "正常运行", "停梯检修", "已停用"]
        ],
    }


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按电梯编号检索"),
    status: str | None = Query(default=None, description="与列表保持同一份筛选条件"),
) -> dict[str, Any]:
    """导出电梯设备清单：条数与列表当前筛选范围一致。"""
    items, total = service.export_entries(keyword=keyword, status=status)
    return {"module": "elevator", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条电梯设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"电梯设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条电梯设备，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="电梯设备已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_use_unit: str | None = Header(default=None, alias="X-Use-Unit"),
) -> ActionResult:
    """对单台电梯执行状态流转；重复提交、跳档、回退与跨单位改动都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    unit = _resolve_unit(payload, x_use_unit)
    entry, message = service.run_action(entry_id, action, acting_unit=unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

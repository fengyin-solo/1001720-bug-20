"""电梯设备业务规则：分页口径、状态流转、归属校验都收在这里。

关键口径：
- 筛选、分页偏移与筛选后总数都由后端在同一次查询里算好，前端不再自行推算。
- 状态只能沿「待投用 → 正常运行 → 停梯检修 → 已停用」单向逐档推进，
  重复提交、跳档、回退一律挡下并说明当前状态。
- 只有归属本单位的使用单位能处置自己名下的电梯，跨单位改动直接拒绝。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "elevator"
DEFAULT_UNIT = "江北分公司"
REQUIRED_FIELDS = ["电梯编号", "电梯名称", "载重规格"]
STATUS_ORDER = ["待投用", "正常运行", "停梯检修", "已停用"]
# 每个动作把状态向前推进一档；不允许直接映射到任意目标状态。
ACTION_RULES = {"办理投用": "正常运行", "安排检修": "停梯检修", "停用电梯": "已停用"}
NEGATIVE_ACTIONS = ["停用电梯"]
DISPLAY_STATUS_FIELD = "电梯状态"


def _filter_rows(
    *,
    keyword: str | None = None,
    status: str | None = None,
    unit: str | None = None,
) -> list[dict[str, Any]]:
    """列表、统计、导出共用的同一份筛选结果，避免各算各的。"""
    rows = store.rows(MODULE)
    if keyword:
        rows = [row for row in rows if keyword in str(row.get("电梯编号", ""))]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    if unit:
        rows = [row for row in rows if str(row.get("使用单位") or DEFAULT_UNIT) == unit]
    return rows


class ElevatorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        """返回当前页数据、筛选后总数、归一化后的页码、总页数（一次算齐）。"""
        filtered = _filter_rows(keyword=keyword, status=status)
        total = len(filtered)
        size = max(size, 1)
        pages = max((total + size - 1) // size, 1)
        # 越界页码回收到最后一页，避免切每页条数后末页漏数据。
        current = min(max(page, 1), pages)
        start = (current - 1) * size
        return filtered[start:start + size], total, current, pages

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """导出与列表「当前条件」一致的全量结果，条数与筛选总数对齐。"""
        filtered = _filter_rows(keyword=keyword, status=status)
        return filtered, len(filtered)

    def summary(self, *, keyword: str | None = None, status: str | None = None) -> dict[str, int]:
        """概览卡片与列表共用同一份筛选结果，台数各归各类。"""
        filtered = _filter_rows(keyword=keyword, status=status)
        counts = {name: 0 for name in STATUS_ORDER}
        for row in filtered:
            name = str(row.get("status"))
            if name in counts:
                counts[name] += 1
        counts["全部"] = len(filtered)
        return counts

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ("电梯编号", "电梯名称", "载重规格", "层站数量", "使用场所", "投用日期", "下次检验日"):
            entry[field] = values.get(field)
        unit = str(values.get("使用单位") or "").strip() or DEFAULT_UNIT
        entry["使用单位"] = unit
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, *, acting_unit: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"电梯设备 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于电梯设备可执行范围"

        unit = str(acting_unit or "").strip() or DEFAULT_UNIT
        owner = str(entry.get("使用单位") or DEFAULT_UNIT)
        if owner != unit:
            return None, (
                f"电梯设备 {entry_id} 归属{owner}，当前单位为{unit}，"
                "跨使用单位不能变更设备状态"
            )

        current = str(entry.get("status") or "")
        target = ACTION_RULES[action]
        try:
            current_index = STATUS_ORDER.index(current)
            target_index = STATUS_ORDER.index(target)
        except ValueError:
            return None, "设备当前状态不在允许的状态序列里，无法继续流转"

        # 只能向相邻的下一档走：重复提交（原地）、跳档、回退都在这里挡下。
        if target_index == current_index:
            return None, f"电梯设备当前为「{current}」，处置已经提交过，请勿重复操作"
        if target_index < current_index:
            return None, (
                f"电梯设备当前为「{current}」，状态只能单向推进，"
                f"不能回退到「{target}」"
            )
        if target_index > current_index + 1:
            return None, (
                f"电梯设备当前为「{current}」，不能跳过中间环节直接「{action}」"
                f"到「{target}」"
            )

        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"电梯设备已{action}，状态由「{current}」更新为「{target}」"

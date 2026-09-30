"""电梯设备业务规则：分页与筛选口径统一收口，状态只允许沿「待检 → 在用 → 停用」单向往下一步。

列表、导出、运营概览都走同一个筛选函数，保证台数、条数、分页总数来自同一份结果；
状态推进在本层集中校验：必须由归属使用单位发起、只能推进到相邻的下一档，
跳档、回退、重复提交都会被拦下并给出带当前状态的说明。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "elevator"
REQUIRED_FIELDS = ["电梯编号", "电梯名称", "载重规格", "使用单位"]
KEYWORD_FIELD = "电梯编号"
DISPLAY_STATUS_FIELD = "电梯状态"

STATUS_PENDING = "待检"
STATUS_IN_USE = "在用"
STATUS_STOPPED = "停用"
STATUS_ORDER = [STATUS_PENDING, STATUS_IN_USE, STATUS_STOPPED]

# 动作只表达「推进到下一档」：(允许发起的当前状态, 动作后的目标状态)
ACTION_RULES: dict[str, tuple[str, str]] = {
    "办理投用": (STATUS_PENDING, STATUS_IN_USE),
    "停用电梯": (STATUS_IN_USE, STATUS_STOPPED),
}

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
# 临近检验窗口：下次检验日落在该天数内（含已逾期）计入运营概览
INSPECT_WARNING_DAYS = 30
# 受保护字段只能由本服务按规则改写，登记/动作接口不得覆盖
PROTECTED_FIELDS = ("id", "status", "pending", "abnormal", DISPLAY_STATUS_FIELD)


class ElevatorService:
    # ---- 列表 / 分页 / 统计共用的筛选口径 -----------------------------------

    def _filtered_rows(
        self,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """列表、导出、概览统计共用：筛选条件一致，结果就必然对得上。"""
        rows = list(store.rows(MODULE))
        if keyword:
            key = keyword.strip()
            if key:
                rows = [row for row in rows if key in str(row.get(KEYWORD_FIELD, ""))]
        if status:
            status = status.strip()
            if status not in STATUS_ORDER:
                return []
            rows = [row for row in rows if row.get("status") == status]
        return rows

    @staticmethod
    def _normalize_page(page: int, size: int, total: int) -> tuple[int, int, int]:
        """页码、每页条数与总页数一次算好：越界页码收敛到最后一页，避免漏条或空页。"""
        size = size if 1 <= size <= MAX_PAGE_SIZE else DEFAULT_PAGE_SIZE
        page = max(page, 1)
        pages = max(1, (total + size - 1) // size)
        page = min(page, pages)
        return page, size, pages

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """返回 (当前页记录, 筛选后总数, 归一化后的页码)，三者由本方法一次算好。"""
        rows = self._filtered_rows(keyword=keyword, status=status)
        total = len(rows)
        page, size, _pages = self._normalize_page(page, size, total)
        start = (page - 1) * size
        return rows[start:start + size], total, page

    def list_all(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """导出用：与列表同一筛选口径下的全量结果。"""
        rows = self._filtered_rows(keyword=keyword, status=status)
        return rows, len(rows)

    def overview_stats(self) -> dict[str, int]:
        """运营概览的电梯台数：直接统计未加筛选的同一份列表结果。"""
        rows = self._filtered_rows()
        stats = {label: 0 for label in STATUS_ORDER}
        stats["total"] = len(rows)
        stats["临近检验"] = sum(1 for row in rows if self._is_inspection_near(row))
        for row in rows:
            label = str(row.get("status"))
            if label in stats:
                stats[label] += 1
        return stats

    @staticmethod
    def _is_inspection_near(row: dict[str, Any]) -> bool:
        raw = str(row.get("下次检验日") or "").strip()
        try:
            target = date.fromisoformat(raw)
        except ValueError:
            return False
        return target <= date.today() + timedelta(days=INSPECT_WARNING_DAYS)

    # ---- 明细与登记 ---------------------------------------------------------

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for key, value in values.items():
            if key not in PROTECTED_FIELDS:
                entry[key] = value
        entry["status"] = STATUS_PENDING
        entry[DISPLAY_STATUS_FIELD] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    # ---- 状态推进（核心规则） -----------------------------------------------

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator_unit: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行状态推进动作。

        返回 (记录, 说明, 是否生效)；重复提交、跳档、回退、跨单位都返回 ok=False，
        说明里带当前状态，且不会改动任何既有业务字段（含载重规格）。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"电梯设备 {entry_id} 不存在或已归档", False

        operator_unit = (operator_unit or "").strip()
        if not operator_unit:
            return None, "未携带操作单位信息，无法核对电梯归属，状态变更被拒绝", False

        owner = str(entry.get("使用单位") or "").strip()
        if owner and owner != operator_unit:
            return (
                None,
                f"电梯 {entry.get(KEYWORD_FIELD, entry_id)} 归属使用单位「{owner}」，"
                f"当前单位「{operator_unit}」无权变更其状态，跨单位操作已拒绝",
                False,
            )

        action = (action or "").strip()
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于电梯设备可执行范围", False

        expected, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        current_index = STATUS_ORDER.index(current) if current in STATUS_ORDER else -1
        target_index = STATUS_ORDER.index(target)

        if current_index < 0:
            return None, f"电梯当前状态「{current}」不在允许的状态序列里，无法{action}", False
        if current_index > target_index:
            return (
                None,
                f"电梯当前状态为「{current}」，状态只能按 待检 → 在用 → 停用 单向往下一步，"
                f"不能回退到「{target}」",
                False,
            )
        if current == target:
            return (
                None,
                f"电梯当前已是「{current}」状态，{action}已提交过，重复提交不再生效",
                False,
            )
        if current != expected:
            return (
                None,
                f"电梯当前状态为「{current}」，需先推进到「{expected}」才能{action}，"
                f"不允许从「{current}」直接跳到「{target}」",
                False,
            )

        # 只改状态相关字段，载重规格等既有业务字段一律不动
        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target == STATUS_PENDING
        entry["abnormal"] = target == STATUS_STOPPED
        return entry, f"电梯设备已{action}，状态由「{current}」变更为「{target}」", True

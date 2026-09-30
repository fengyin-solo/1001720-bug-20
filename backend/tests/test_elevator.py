"""电梯设备分页、状态流转与归属校验的回归测试。

直接用 FastAPI TestClient 起应用，每个用例前重置内存仓库，避免用例间互相污染。
运行：cd backend && .venv/bin/python -m pytest tests/
（未装 pytest 时也可直接执行：.venv/bin/python tests/test_elevator.py）
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import SEED_ROWS  # noqa: E402
from app.store import store  # noqa: E402

JIANG_BEI = "江北分公司"
JIANG_NAN = "江南分公司"


def reset_store() -> None:
    for name, rows in SEED_ROWS.items():
        store._tables[name] = [dict(row) for row in rows]


def act(client: TestClient, entry_id: int, action: str, unit: str | None = None):
    body = {"values": {"action": action}}
    headers = {}
    if unit:
        body["values"]["使用单位"] = unit
        headers["X-Use-Unit"] = quote(unit)
    return client.post(f"/api/elevator/{entry_id}/actions", json=body, headers=headers)


# ---------------------------------------------------------------- pagination
def test_pages_do_not_overlap_and_total_matches():
    reset_store()
    client = TestClient(app)
    first = client.get("/api/elevator", params={"page": 1, "size": 10}).json()
    second = client.get("/api/elevator", params={"page": 2, "size": 10}).json()
    third = client.get("/api/elevator", params={"page": 3, "size": 10}).json()

    ids = [
        [item["id"] for item in page["items"]]
        for page in (first, second, third)
    ]
    # 翻页不重复：相邻两页没有同一条记录。
    assert not set(ids[0]) & set(ids[1])
    assert not set(ids[1]) & set(ids[2])
    # 页码、行数、总数对得上。
    assert first["total"] == second["total"] == third["total"] == 23
    assert (len(ids[0]), len(ids[1]), len(ids[2])) == (10, 10, 3)
    assert first["pages"] == second["pages"] == third["pages"] == 3


def test_page_beyond_last_is_clamped_not_dropped():
    reset_store()
    client = TestClient(app)
    # 每页 20 条时只要 2 页；请求第 9 页要回收到第 2 页而不是返回空。
    data = client.get("/api/elevator", params={"page": 9, "size": 20}).json()
    assert data["page"] == 2
    assert data["pages"] == 2
    assert len(data["items"]) == 3


def test_filtered_total_and_export_share_one_result():
    reset_store()
    client = TestClient(app)
    params = {"status": "已停用", "page": 1, "size": 2}
    page = client.get("/api/elevator", params=params).json()
    export = client.get("/api/elevator/export", params={"status": "已停用"}).json()
    stats = client.get("/api/elevator/stats", params={"status": "已停用"}).json()
    overview = client.get("/api/overview").json()
    elevator_overview = next(m for m in overview["modules"] if m["name"] == "elevator")

    assert page["total"] == 3
    assert export["total"] == page["total"]
    assert len(export["items"]) == export["total"]
    assert stats["total"] == page["total"]
    # 运营概览的电梯台数与列表无筛选总数同源。
    assert elevator_overview["created"] == 23


# --------------------------------------------------------------- state machine
def test_status_moves_forward_one_step_only():
    reset_store()
    client = TestClient(app)
    # id1：待投用 -> 正常运行 -> 停梯检修 -> 已停用
    assert act(client, 1, "办理投用", JIANG_BEI).json()["ok"]
    assert act(client, 1, "安排检修", JIANG_BEI).json()["ok"]
    assert act(client, 1, "停用电梯", JIANG_BEI).json()["ok"]
    detail = client.get("/api/elevator/1").json()
    assert detail["status"] == "已停用"
    # 列表状态展示字段同步成最新状态。
    assert detail["电梯状态"] == "已停用"


def test_duplicate_submission_only_takes_effect_once():
    reset_store()
    client = TestClient(app)
    first = act(client, 1, "办理投用", JIANG_BEI).json()
    second = act(client, 1, "办理投用", JIANG_BEI).json()
    assert first["ok"] is True
    assert second["ok"] is False
    assert "重复" in second["message"]


def test_jump_ahead_is_rejected_with_current_status():
    reset_store()
    client = TestClient(app)
    result = act(client, 4, "停用电梯", JIANG_BEI).json()
    assert result["ok"] is False
    assert "待投用" in result["message"]
    assert client.get("/api/elevator/4").json()["status"] == "待投用"


def test_rollback_is_rejected():
    reset_store()
    client = TestClient(app)
    act(client, 1, "办理投用", JIANG_BEI)
    act(client, 1, "安排检修", JIANG_BEI)
    # 停梯检修后再办理投用（目标状态落在当前状态之前）要按回退挡下。
    result = act(client, 1, "办理投用", JIANG_BEI).json()
    assert result["ok"] is False
    assert "不能回退" in result["message"]
    assert "停梯检修" in result["message"]


# ----------------------------------------------------------------- ownership
def test_cross_unit_change_is_rejected():
    reset_store()
    client = TestClient(app)
    # id3 归属江南分公司，江北分公司不能停用。
    result = act(client, 3, "停用电梯", JIANG_BEI).json()
    assert result["ok"] is False
    assert "跨使用单位" in result["message"]
    assert JIANG_NAN in result["message"]
    # 归属单位自己可以处置。
    assert act(client, 3, "停用电梯", JIANG_NAN).json()["ok"] is True


def test_unit_can_be_sent_via_header():
    reset_store()
    client = TestClient(app)
    response = client.post(
        "/api/elevator/1/actions",
        json={"values": {"action": "办理投用"}},
        headers={"X-Use-Unit": quote(JIANG_BEI)},
    )
    assert response.json()["ok"] is True


def test_load_spec_is_preserved_after_actions():
    reset_store()
    client = TestClient(app)
    original = {
        row["id"]: row["载重规格"] for row in SEED_ROWS["elevator"] if row["id"] in (1, 2, 3)
    }
    act(client, 1, "办理投用", JIANG_BEI)
    act(client, 3, "停用电梯", JIANG_NAN)
    for entry_id, spec in original.items():
        assert client.get(f"/api/elevator/{entry_id}").json()["载重规格"] == spec


def _run_all() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run_all()

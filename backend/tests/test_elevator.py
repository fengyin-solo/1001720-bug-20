"""电梯设备模块回归测试：分页口径、状态单向流转、归属校验、清单一致性。

运行：backend/ 目录下 pytest（需安装 pytest、httpx）。
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # 每个用例按依赖顺序重新导入，重置内存仓库，避免状态在用例间串扰
    import app.seed
    import app.store
    import app.services.elevator
    import app.routers.elevator
    import app.main

    importlib.reload(app.seed)
    importlib.reload(app.store)
    importlib.reload(app.services.elevator)
    importlib.reload(app.routers.elevator)
    importlib.reload(app.main)
    return TestClient(app.main.app)


def act(client: TestClient, entry_id: int, action: str, unit: str | None):
    params = {"operatorUnit": unit} if unit else {}
    return client.post(
        f"/api/elevator/{entry_id}/actions",
        json={"values": {"action": action}},
        params=params,
    )


# ---- 分页：偏移、总数、页码由后端一次算好 ---------------------------------

def test_pages_do_not_overlap_and_cover_all(client: TestClient) -> None:
    seen: list[int] = []
    first = client.get("/api/elevator", params={"page": 1, "size": 20}).json()
    assert first["total"] == 26
    assert first["page"] == 1
    assert len(first["items"]) == 20
    seen.extend(item["id"] for item in first["items"])

    second = client.get("/api/elevator", params={"page": 2, "size": 20}).json()
    assert len(second["items"]) == 6
    seen.extend(item["id"] for item in second["items"])

    # 两页之间没有重复，且恰好覆盖全部记录
    assert len(seen) == len(set(seen)) == 26


def test_page_beyond_range_clamps_to_last_page(client: TestClient) -> None:
    resp = client.get("/api/elevator", params={"page": 99, "size": 10}).json()
    assert resp["page"] == 3
    assert resp["total"] == 26
    assert len(resp["items"]) == 6


def test_last_page_with_smaller_size_not_losing_rows(client: TestClient) -> None:
    # size=10 时最后一页是第 3 页，包含第 21~26 条
    resp = client.get("/api/elevator", params={"page": 3, "size": 10}).json()
    assert [item["id"] for item in resp["items"]] == [21, 22, 23, 24, 25, 26]


def test_filtered_total_matches_rows_returned(client: TestClient) -> None:
    resp = client.get("/api/elevator", params={"status": "待检", "page": 1, "size": 5}).json()
    assert resp["total"] == 9
    assert len(resp["items"]) == 5
    assert all(item["status"] == "待检" for item in resp["items"])

    # 筛选后页码越界同样收敛到筛选结果的最后一页
    last = client.get("/api/elevator", params={"status": "待检", "page": 9, "size": 5}).json()
    assert last["page"] == 2
    assert len(last["items"]) == 4


def test_size_over_limit_rejected(client: TestClient) -> None:
    resp = client.get("/api/elevator", params={"size": 201})
    assert resp.status_code == 400


def test_keyword_filter(client: TestClient) -> None:
    resp = client.get("/api/elevator", params={"keyword": "ELEV-002"}).json()
    assert resp["total"] == 7  # ELEV-0020 ~ ELEV-0026
    assert all("ELEV-002" in item["电梯编号"] for item in resp["items"])


# ---- 状态只能 待检 → 在用 → 停用 单向往下一步 ------------------------------

def test_status_flow_forward(client: TestClient) -> None:
    r1 = act(client, 1, "办理投用", "华辰制药厂")
    assert r1.json()["ok"] is True
    assert r1.json()["entry"]["status"] == "在用"

    r2 = act(client, 1, "停用电梯", "华辰制药厂")
    assert r2.json()["ok"] is True
    assert r2.json()["entry"]["status"] == "停用"


def test_skip_status_rejected_with_current_state(client: TestClient) -> None:
    # id=1 为待检，直接停用属于跳档
    resp = act(client, 1, "停用电梯", "华辰制药厂")
    body = resp.json()
    assert body["ok"] is False
    assert "待检" in body["message"]
    assert client.get("/api/elevator/1").json()["status"] == "待检"


def test_rollback_rejected_with_current_state(client: TestClient) -> None:
    # id=3 为停用，投用属于回退
    resp = act(client, 3, "办理投用", "江南纺织有限公司")
    body = resp.json()
    assert body["ok"] is False
    assert "回退" in body["message"]
    assert "停用" in body["message"]


def test_duplicate_action_applies_once(client: TestClient) -> None:
    r1 = act(client, 1, "办理投用", "华辰制药厂")
    assert r1.json()["ok"] is True
    r2 = act(client, 1, "办理投用", "华辰制药厂")
    body = r2.json()
    assert body["ok"] is False
    assert "重复提交" in body["message"]
    assert client.get("/api/elevator/1").json()["status"] == "在用"


def test_load_spec_untouched_by_action(client: TestClient) -> None:
    before = client.get("/api/elevator/1").json()
    act(client, 1, "办理投用", "华辰制药厂")
    after = client.get("/api/elevator/1").json()
    assert after["载重规格"] == before["载重规格"]
    assert after["电梯编号"] == before["电梯编号"]
    assert after["层站数量"] == before["层站数量"]


# ---- 归属校验：只有本单位能改自己名下电梯 ---------------------------------

def test_cross_unit_change_rejected(client: TestClient) -> None:
    # id=3 归属江南纺织有限公司
    resp = act(client, 3, "办理投用", "华辰制药厂")
    body = resp.json()
    assert body["ok"] is False
    assert "归属" in body["message"] and "跨单位" in body["message"]
    assert client.get("/api/elevator/3").json()["status"] == "停用"


def test_owner_unit_change_allowed(client: TestClient) -> None:
    # id=2 归属华辰制药厂，当前在用，可由本单位停用
    resp = act(client, 2, "停用电梯", "华辰制药厂")
    assert resp.json()["ok"] is True


def test_missing_unit_rejected(client: TestClient) -> None:
    resp = act(client, 1, "办理投用", None)
    assert resp.json()["ok"] is False


# ---- 运营概览、列表、导出同一份结果 ----------------------------------------

def test_overview_matches_unfiltered_list(client: TestClient) -> None:
    overview = client.get("/api/overview").json()["elevator"]
    listing = client.get("/api/elevator", params={"page": 1, "size": 200}).json()
    stats_endpoint = client.get("/api/elevator/stats").json()
    assert overview["total"] == listing["total"] == stats_endpoint["total"] == 26


def test_export_count_matches_current_filter_scope(client: TestClient) -> None:
    status = "停用"
    export_resp = client.get("/api/elevator/export", params={"status": status}).json()
    list_resp = client.get("/api/elevator", params={"status": status, "size": 200}).json()
    assert export_resp["total"] == list_resp["total"]
    assert len(export_resp["items"]) == export_resp["total"]
    assert {item["id"] for item in export_resp["items"]} == {
        item["id"] for item in list_resp["items"]
    }


def test_detail_reflects_latest_status(client: TestClient) -> None:
    act(client, 1, "办理投用", "华辰制药厂")
    # 列表与详情都来自同一个内存仓库，状态保持最新
    listing = client.get("/api/elevator", params={"page": 1, "size": 20}).json()
    row = next(item for item in listing["items"] if item["id"] == 1)
    detail = client.get("/api/elevator/1").json()
    assert row["status"] == detail["status"] == "在用"
    assert detail["电梯状态"] == "在用"

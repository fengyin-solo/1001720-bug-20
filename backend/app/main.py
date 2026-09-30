"""特种设备点检运维平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.services.elevator import ElevatorService
from app.store import store

elevator_service = ElevatorService()

app = FastAPI(title="特种设备点检运维平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    电梯设备的台数与列表取自同一份结果（电梯服务的无筛选总数），
    不再让概览与列表各算各的。
    """
    data = store.overview()
    elevator_total = elevator_service.summary()["全部"]
    for item in data["modules"]:
        if item["name"] == "elevator":
            item["created"] = elevator_total
    for card in data["cards"]:
        if card["label"] == "今日新增":
            card["value"] = sum(int(item["created"]) for item in data["modules"])
    return data

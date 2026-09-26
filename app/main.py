"""定尺线材开料、单台锯床排产与成品检验 API。

启动后见 http://localhost:8000/docs 交互式文档。
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .inspector import inspect
from .planner import plan
from .scheduler import schedule
from .validation import (
    RequestError,
    parse_inspection_request,
    parse_request,
    parse_schedule_request,
)

app = FastAPI(
    title="定尺线材开料 API",
    description=(
        "POST /plans：根据原料长度、锯缝宽度与成品清单，计算全局最少原料根数的下料方案；"
        "POST /schedules：为 /plans 返回的 bars 安排单台锯床加工顺序，最小化最大逾期；"
        "POST /inspections：按 /plans 的 bars 逐根核对实测成品长度并判定合格。"
    ),
    version="1.2.0",
)


@app.exception_handler(RequestError)
async def request_error_handler(_request: Request, exc: RequestError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/plans")
async def create_plan(request: Request) -> dict[str, object]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError("请求体不是合法的 JSON 对象")
    stock_length, kerf, items = parse_request(body)
    bars = plan(stock_length, kerf, items)
    return {
        "stock_length": stock_length,
        "kerf": kerf,
        "bar_count": len(bars),
        "bars": bars,
    }


@app.post("/schedules")
async def create_schedule(request: Request) -> dict[str, object]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError("请求体不是合法的 JSON 对象")
    bars, jobs, initial_blade, changeover = parse_schedule_request(body)
    return {
        "initial_blade": initial_blade,
        "changeover": changeover,
        **schedule(bars, jobs, initial_blade, changeover),
    }


@app.post("/inspections")
async def create_inspection(request: Request) -> dict[str, object]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError("请求体不是合法的 JSON 对象")
    bars, items, measurements, tolerance = parse_inspection_request(body)
    return {
        "tolerance": tolerance,
        **inspect(bars, items, measurements, tolerance),
    }

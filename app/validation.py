"""请求体的严格解析与校验。

直接对原始 JSON 做校验（而非依赖 Pydantic 宽松转换），以便对
``5.0``、``"12"``、布尔值、非法结构等明确报错。
"""

from __future__ import annotations

from typing import Any

from .planner import MAX_ITEMS
from .scheduler import MAX_BARS


class RequestError(ValueError):
    """请求非法；由 API 层转换为 HTTP 422。"""


# 仅接受这些顶层字段，多余字段一律报错（通常是拼写错误）。
_ALLOWED_TOP_FIELDS = {"stock_length", "kerf", "items"}
_ALLOWED_ITEM_FIELDS = {"id", "length"}

# POST /schedules 的字段约定。
_ALLOWED_SCHEDULE_FIELDS = {"bars", "jobs", "initial_blade", "changeover"}
# bars 直接接收 /plans 的返回元素；后两个字段可选校验（存在时必须合法）。
_ALLOWED_BAR_FIELDS = {"item_ids", "occupied_length", "remaining_length"}
_ALLOWED_JOB_FIELDS = {"duration", "release", "due", "blade"}


def parse_request(body: Any) -> tuple[int, int, list[tuple[str, int]]]:
    """校验并返回 (原料长度, 锯缝宽度, [(id, 长度), ...])。"""
    if not isinstance(body, dict):
        raise RequestError("请求体必须是 JSON 对象")

    unexpected = set(body) - _ALLOWED_TOP_FIELDS
    if unexpected:
        raise RequestError(f"存在非法字段：{sorted(unexpected)}")
    if "stock_length" not in body:
        raise RequestError("缺少必填字段 stock_length")
    if "kerf" not in body:
        raise RequestError("缺少必填字段 kerf")
    if "items" not in body:
        raise RequestError("缺少必填字段 items")

    stock_length = _parse_strict_int(body["stock_length"], "stock_length")
    if stock_length <= 0:
        raise RequestError("stock_length 必须为正整数")

    kerf = _parse_strict_int(body["kerf"], "kerf")
    if kerf < 0:
        raise RequestError("kerf 必须为非负整数")

    raw_items = body["items"]
    if not isinstance(raw_items, list):
        raise RequestError("items 必须是数组")
    if not 1 <= len(raw_items) <= MAX_ITEMS:
        raise RequestError(f"items 件数必须在 1 到 {MAX_ITEMS} 之间")

    items: list[tuple[str, int]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        location = f"items[{index}]"
        if not isinstance(raw_item, dict):
            raise RequestError(f"{location} 必须是对象")

        unexpected_item = set(raw_item) - _ALLOWED_ITEM_FIELDS
        if unexpected_item:
            raise RequestError(
                f"{location} 存在非法字段：{sorted(unexpected_item)}"
            )
        if "id" not in raw_item:
            raise RequestError(f"{location} 缺少必填字段 id")
        if "length" not in raw_item:
            raise RequestError(f"{location} 缺少必填字段 length")

        item_id = raw_item["id"]
        if not isinstance(item_id, str):
            raise RequestError(f"{location}.id 必须是字符串")

        length = _parse_strict_int(raw_item["length"], f"{location}.length")
        if length <= 0:
            raise RequestError(f"{location}.length 必须为正整数")

        if item_id in seen_ids:
            raise RequestError(f"成品 id 重复：{item_id!r}")
        seen_ids.add(item_id)

        if length > stock_length:
            raise RequestError(
                f"{location}（id={item_id!r}）长度 {length} 超过原料长度 "
                f"{stock_length}，无法下料"
            )

        items.append((item_id, length))

    return stock_length, kerf, items


def _parse_strict_int(value: Any, field: str) -> int:
    """仅接受真正的整数；布尔值、浮点（含 5.0）、字符串一律拒绝。"""
    # bool 是 int 的子类，必须先排除。
    if isinstance(value, bool) or not isinstance(value, int):
        raise RequestError(f"{field} 必须是整数")
    return value


def _parse_non_empty_str(value: Any, field: str) -> str:
    """仅接受非空字符串。"""
    if not isinstance(value, str) or value == "":
        raise RequestError(f"{field} 必须是非空字符串")
    return value


def parse_schedule_request(
    body: Any,
) -> tuple[list[dict[str, Any]], list[tuple[int, int, int, str]], str, int]:
    """校验 POST /schedules 请求。

    返回 (bars, jobs, initial_blade, changeover)；jobs[i] 为
    (duration, release, due, blade)，与 bars[i] 一一对应。
    """
    if not isinstance(body, dict):
        raise RequestError("请求体必须是 JSON 对象")

    unexpected = set(body) - _ALLOWED_SCHEDULE_FIELDS
    if unexpected:
        raise RequestError(f"存在非法字段：{sorted(unexpected)}")
    for name in ("bars", "jobs", "initial_blade", "changeover"):
        if name not in body:
            raise RequestError(f"缺少必填字段 {name}")

    initial_blade = _parse_non_empty_str(body["initial_blade"], "initial_blade")

    changeover = _parse_strict_int(body["changeover"], "changeover")
    if changeover < 0:
        raise RequestError("changeover 必须为非负整数")

    raw_bars = body["bars"]
    if not isinstance(raw_bars, list):
        raise RequestError("bars 必须是数组")
    if not 1 <= len(raw_bars) <= MAX_BARS:
        raise RequestError(f"bars 根数必须在 1 到 {MAX_BARS} 之间")

    raw_jobs = body["jobs"]
    if not isinstance(raw_jobs, list):
        raise RequestError("jobs 必须是数组")
    if len(raw_jobs) != len(raw_bars):
        raise RequestError("jobs 与 bars 必须等长且一一对应")

    bars: list[dict[str, Any]] = []
    for index, raw_bar in enumerate(raw_bars):
        location = f"bars[{index}]"
        if not isinstance(raw_bar, dict):
            raise RequestError(f"{location} 必须是对象")

        unexpected_bar = set(raw_bar) - _ALLOWED_BAR_FIELDS
        if unexpected_bar:
            raise RequestError(
                f"{location} 存在非法字段：{sorted(unexpected_bar)}"
            )
        if "item_ids" not in raw_bar:
            raise RequestError(f"{location} 缺少必填字段 item_ids")

        item_ids = raw_bar["item_ids"]
        if not isinstance(item_ids, list) or not item_ids:
            raise RequestError(f"{location}.item_ids 必须是非空数组")
        for sub_index, item_id in enumerate(item_ids):
            if not isinstance(item_id, str):
                raise RequestError(
                    f"{location}.item_ids[{sub_index}] 必须是字符串"
                )

        # 透传 /plans 的两个可选字段；出现时仍做严格整数校验。
        for opt_field in ("occupied_length", "remaining_length"):
            if opt_field in raw_bar:
                value = _parse_strict_int(raw_bar[opt_field], f"{location}.{opt_field}")
                if value < 0:
                    raise RequestError(f"{location}.{opt_field} 必须为非负整数")

        bars.append(raw_bar)

    jobs: list[tuple[int, int, int, str]] = []
    for index, raw_job in enumerate(raw_jobs):
        location = f"jobs[{index}]"
        if not isinstance(raw_job, dict):
            raise RequestError(f"{location} 必须是对象")

        unexpected_job = set(raw_job) - _ALLOWED_JOB_FIELDS
        if unexpected_job:
            raise RequestError(
                f"{location} 存在非法字段：{sorted(unexpected_job)}"
            )
        for name in ("duration", "release", "due", "blade"):
            if name not in raw_job:
                raise RequestError(f"{location} 缺少必填字段 {name}")

        duration = _parse_strict_int(raw_job["duration"], f"{location}.duration")
        if duration <= 0:
            raise RequestError(f"{location}.duration 必须为正整数")

        release = _parse_strict_int(raw_job["release"], f"{location}.release")
        if release < 0:
            raise RequestError(f"{location}.release 必须为非负整数")

        due = _parse_strict_int(raw_job["due"], f"{location}.due")
        if due < 0:
            raise RequestError(f"{location}.due 必须为非负整数")

        blade = _parse_non_empty_str(raw_job["blade"], f"{location}.blade")

        jobs.append((duration, release, due, blade))

    return bars, jobs, initial_blade, changeover

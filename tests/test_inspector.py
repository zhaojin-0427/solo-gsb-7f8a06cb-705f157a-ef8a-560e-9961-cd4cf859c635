"""inspector 单元测试，并用小规模暴力枚举对拍。"""

from __future__ import annotations

import random

from app.inspector import _match_bar, inspect


def _brute_force(planned, measured, tolerance):
    """枚举全部一对一配对，返回最优 (pairs, missing, leftover)。

    最优键：(-配对数, 绝对偏差和, 按 id 升序的 (id, 实测下标) 列表)。
    """
    best = None  # (最优键, pairs)

    def recurse(i, used, deviation, pairs):
        nonlocal best
        if i == len(planned):
            key = (-len(pairs), deviation, tuple(pairs))
            if best is None or key < best[0]:
                best = (key, list(pairs))
            return
        item_id, length = planned[i]
        # 本件不配对。
        recurse(i + 1, used, deviation, pairs)
        for index, got in enumerate(measured):
            if index in used:
                continue
            delta = abs(got - length)
            if delta <= tolerance:
                recurse(i + 1, used | {index}, deviation + delta, pairs + [(item_id, index)])

    recurse(0, set(), 0, [])
    pairs = best[1]
    matched_ids = {item_id for item_id, _ in pairs}
    used = {index for _, index in pairs}
    missing = [item_id for item_id, _ in planned if item_id not in matched_ids]
    leftover = [index for index in range(len(measured)) if index not in used]
    return pairs, missing, leftover


def test_empty_measurements_all_missing():
    pairs, missing, leftover = _match_bar([("a", 10), ("b", 20)], [], 5)
    assert pairs == []
    assert missing == ["a", "b"]
    assert leftover == []


def test_exact_match_single_pair():
    pairs, missing, leftover = _match_bar([("a", 10)], [10], 0)
    assert pairs == [("a", 0)]
    assert missing == []
    assert leftover == []


def test_tolerance_boundary():
    # |13 - 10| = 3 恰等于公差，允许配对。
    pairs, _, _ = _match_bar([("a", 10)], [13], 3)
    assert pairs == [("a", 0)]
    # 公差 2 时不可配对。
    pairs, missing, leftover = _match_bar([("a", 10)], [13], 2)
    assert pairs == []
    assert missing == ["a"]
    assert leftover == [0]


def test_pair_count_beats_deviation():
    # 2 对（偏差和 5）优于 1 对（偏差和 0）。
    planned = [("a", 10), ("b", 20)]
    pairs, missing, leftover = _match_bar(planned, [10, 15], 5)
    assert pairs == [("a", 0), ("b", 1)]
    assert missing == []
    assert leftover == []


def test_deviation_tiebreak():
    # 两种 2 对配法：偏差和 2 优于 6。
    planned = [("a", 10), ("b", 13)]
    pairs, _, _ = _match_bar(planned, [11, 14], 5)
    assert pairs == [("a", 0), ("b", 1)]


def test_lexicographic_tiebreak():
    # 完全对称：取 (id, 实测下标) 列表字典序最小者。
    planned = [("a", 10), ("b", 10)]
    pairs, _, _ = _match_bar(planned, [10, 10], 0)
    assert pairs == [("a", 0), ("b", 1)]


def test_lexicographic_prefers_smaller_id_subset():
    # 只能配 1 对且偏差相同：配 id 更小的 a。
    planned = [("a", 10), ("b", 10)]
    pairs, missing, leftover = _match_bar(planned, [10], 0)
    assert pairs == [("a", 0)]
    assert missing == ["b"]
    assert leftover == []


def test_random_against_brute_force():
    rng = random.Random(20260926)
    for _ in range(400):
        k = rng.randint(1, 6)
        m = rng.randint(0, 6)
        planned = [(f"i{i}", rng.randint(1, 20)) for i in range(k)]
        measured = [rng.randint(1, 20) for _ in range(m)]
        tolerance = rng.randint(0, 6)
        assert _match_bar(planned, measured, tolerance) == _brute_force(
            planned, measured, tolerance
        )


def test_inspect_aggregates_bars_and_qualification():
    items = [("A", 100), ("B", 200), ("C", 300)]
    bars = [["A"], ["B", "C"]]
    measurements = [[101], [200, 295]]
    result = inspect(items, bars, measurements, 5)
    assert result["bar_count"] == 2
    assert result["qualified"] is True
    assert result["bars"][0]["pairs"] == [
        {"id": "A", "measurement": 0, "deviation": 1}
    ]
    assert result["bars"][1]["pairs"] == [
        {"id": "B", "measurement": 0, "deviation": 0},
        {"id": "C", "measurement": 1, "deviation": -5},
    ]

    # 第二根缺 C 且多一条实测：整单不合格。
    result = inspect(items, bars, [[101], [200, 290, 999]], 5)
    assert result["qualified"] is False
    assert result["bars"][1]["missing"] == ["C"]
    assert result["bars"][1]["leftover"] == [1, 2]

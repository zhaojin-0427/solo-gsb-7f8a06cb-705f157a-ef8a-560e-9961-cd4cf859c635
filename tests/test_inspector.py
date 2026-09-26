"""inspector 单元测试，并用独立实现的暴力枚举对拍。"""

from __future__ import annotations

import random
import time

from app.inspector import inspect


def _brute_force(ids, nominal, observed, tolerance):
    """枚举全部一对一配对，按 (配对数↑, 偏差和↑, 配对列表↑) 取最优。

    返回 (配对 [(id, 实测下标)], 缺件 id, 余件下标)。配对按 id 升序生成，
    键里取 -配对数，使 Python 元组最小值即配对数最大者。
    """
    best = None

    def recurse(i, used_mask, pairs, cost, count):
        nonlocal best
        if i == len(ids):
            key = (-count, cost, tuple(pairs))
            if best is None or key < best[0]:
                best = (key, list(pairs), used_mask)
            return
        # 本件缺件。
        recurse(i + 1, used_mask, pairs, cost, count)
        for j in range(len(observed)):
            if used_mask & (1 << j):
                continue
            diff = abs(observed[j] - nominal[i])
            if diff <= tolerance:
                recurse(
                    i + 1,
                    used_mask | (1 << j),
                    pairs + [(ids[i], j)],
                    cost + diff,
                    count + 1,
                )

    recurse(0, 0, [], 0, 0)
    _, pairs, used_mask = best
    paired_ids = {gid for gid, _ in pairs}
    missing = [gid for gid in ids if gid not in paired_ids]
    surplus = [j for j in range(len(observed)) if not used_mask & (1 << j)]
    return pairs, missing, surplus


def _check(ids, nominal, observed, tolerance):
    bars = [{"item_ids": list(ids)}]
    items = list(zip(ids, nominal))
    result = inspect(bars, items, [list(observed)], tolerance)
    entry = result["inspections"][0]

    expected_pairs, expected_missing, expected_surplus = _brute_force(
        ids, nominal, observed, tolerance
    )
    assert [(p["id"], p["measurement_index"]) for p in entry["pairs"]] == expected_pairs
    assert entry["missing_ids"] == expected_missing
    assert entry["surplus_measurements"] == expected_surplus

    # 有符号偏差 = 实测 − 标称；绝对偏差不超过容差。
    length_by_id = dict(items)
    for pair in entry["pairs"]:
        deviation = observed[pair["measurement_index"]] - length_by_id[pair["id"]]
        assert pair["deviation"] == deviation
        assert abs(deviation) <= tolerance

    # 下标/件互不重复，缺件与余件互补。
    assert len({p["id"] for p in entry["pairs"]}) == len(entry["pairs"])
    assert len({p["measurement_index"] for p in entry["pairs"]}) == len(entry["pairs"])
    used_indices = {p["measurement_index"] for p in entry["pairs"]}
    assert set(entry["surplus_measurements"]) == set(range(len(observed))) - used_indices
    paired_ids = {p["id"] for p in entry["pairs"]}
    assert set(entry["missing_ids"]) == set(ids) - paired_ids

    expected_qualified = not expected_missing and not expected_surplus
    assert entry["qualified"] is expected_qualified
    assert result["qualified"] is expected_qualified
    return result


def test_random_small_instances_match_brute_force():
    rng = random.Random(20260926)
    for _ in range(500):
        m = rng.randint(1, 7)
        k = rng.randint(0, 7)
        ids = [f"i{j}" for j in range(m)]
        nominal = [rng.randint(1, 12) for _ in range(m)]
        observed = [rng.randint(1, 12) for _ in range(k)]
        tolerance = rng.randint(0, 4)
        _check(ids, nominal, observed, tolerance)


def test_pair_count_has_top_priority():
    # 若追求最小偏差只会配 1 件（11↔a=10 偏差1），但配 2 件才最优：
    # b=12 只能与 11（偏差1）配，a 只能与 10（偏差0）配。
    result = _check(["a", "b"], [10, 12], [11, 10], 1)
    pairs = result["inspections"][0]["pairs"]
    assert [(p["id"], p["measurement_index"]) for p in pairs] == [
        ("a", 1),
        ("b", 0),
    ]


def test_total_absolute_deviation_breaks_count_tie():
    # 两种配法都成对：正配 a→10,b→12 偏差和 0；交叉偏差和 3，取正配。
    result = _check(["a", "b"], [10, 12], [10, 12], 2)
    pairs = result["inspections"][0]["pairs"]
    assert [(p["id"], p["measurement_index"]) for p in pairs] == [
        ("a", 0),
        ("b", 1),
    ]


def test_lexicographic_pair_list_breaks_final_tie():
    # 标称相同、实测相同：配对数与偏差和全平，
    # (a,0),(b,1) 字典序小于 (a,1),(b,0)。
    result = _check(["a", "b"], [10, 10], [10, 10], 0)
    pairs = result["inspections"][0]["pairs"]
    assert [(p["id"], p["measurement_index"]) for p in pairs] == [
        ("a", 0),
        ("b", 1),
    ]


def test_lex_tie_where_pairing_smallest_id_first_is_not_greedy_obvious():
    # a,b=10；实测 10、9，容差1：两种满配偏差和都是 1，取 a 配下标 0。
    result = _check(["a", "b"], [10, 10], [10, 9], 1)
    pairs = result["inspections"][0]["pairs"]
    assert [(p["id"], p["measurement_index"]) for p in pairs] == [
        ("a", 0),
        ("b", 1),
    ]


def test_signed_deviation_sign():
    result = _check(["a", "b"], [10, 10], [7, 13], 3)
    by_id = {p["id"]: p["deviation"] for p in result["inspections"][0]["pairs"]}
    assert by_id == {"a": -3, "b": 3}


def test_tolerance_boundary_is_inclusive():
    result = _check(["a"], [10], [7], 3)
    assert result["inspections"][0]["pairs"][0]["deviation"] == -3
    result = _check(["a"], [10], [13], 3)
    assert result["inspections"][0]["pairs"][0]["deviation"] == 3
    # 差 4 超过容差：缺件 + 余件，不合格。
    result = _check(["a"], [10], [6], 3)
    entry = result["inspections"][0]
    assert entry["pairs"] == []
    assert entry["missing_ids"] == ["a"]
    assert entry["surplus_measurements"] == [0]
    assert entry["qualified"] is False


def test_empty_measurements_all_missing():
    result = _check(["a", "b"], [10, 20], [], 5)
    entry = result["inspections"][0]
    assert entry["pairs"] == []
    assert entry["missing_ids"] == ["a", "b"]
    assert entry["surplus_measurements"] == []
    assert result["qualified"] is False


def test_more_measurements_than_items_leaves_surplus():
    result = _check(["a"], [10], [10, 10, 10], 0)
    entry = result["inspections"][0]
    assert [(p["id"], p["measurement_index"]) for p in entry["pairs"]] == [("a", 0)]
    assert entry["missing_ids"] == []
    assert entry["surplus_measurements"] == [1, 2]
    assert entry["qualified"] is False


def test_bars_do_not_share_measurements():
    # bar0 的两件与 1 条实测（只能配 b），bar1 无实测：不跨根借配。
    bars = [{"item_ids": ["a", "b"]}, {"item_ids": ["c"]}]
    items = [("a", 10), ("b", 5), ("c", 5)]
    result = inspect(bars, items, [[5], []], 0)
    first, second = result["inspections"]
    assert [(p["id"], p["measurement_index"]) for p in first["pairs"]] == [("b", 0)]
    assert first["missing_ids"] == ["a"]
    assert first["surplus_measurements"] == []
    assert second["pairs"] == []
    assert second["missing_ids"] == ["c"]
    assert result["qualified"] is False


def test_bar_item_ids_need_not_be_sorted():
    # bar 内 id 顺序乱序给出时，结果仍按 id 升序组织。
    bars = [{"item_ids": ["b", "a"]}]
    result = inspect(bars, [("a", 10), ("b", 5)], [[5, 10]], 0)
    pairs = result["inspections"][0]["pairs"]
    assert [(p["id"], p["measurement_index"]) for p in pairs] == [
        ("a", 1),
        ("b", 0),
    ]


def test_qualified_when_every_bar_perfect():
    bars = [{"item_ids": ["a"]}, {"item_ids": ["b", "c"]}]
    items = [("a", 10), ("b", 20), ("c", 30)]
    result = inspect(bars, items, [[11], [20, 31]], 1)
    assert all(entry["qualified"] for entry in result["inspections"])
    assert result["qualified"] is True


def test_fourteen_items_performance():
    rng = random.Random(99)
    ids = [f"ID-{i:02d}" for i in range(14)]
    nominal = [rng.randint(100, 500) for _ in range(14)]
    observed = [value + rng.randint(-2, 2) for value in nominal]
    bars = [{"item_ids": ids}]
    items = list(zip(ids, nominal))
    start = time.perf_counter()
    result = inspect(bars, items, [observed], 2)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    assert len(result["inspections"][0]["pairs"]) == 14
    assert result["qualified"] is True

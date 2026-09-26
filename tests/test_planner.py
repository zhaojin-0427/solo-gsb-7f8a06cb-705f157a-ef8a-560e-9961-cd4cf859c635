"""planner 单元测试，并用小规模暴力枚举对拍。"""

from __future__ import annotations

import itertools
import random
import time

from app.planner import plan


def _occupied(group_ids, length_by_id, kerf):
    return sum(length_by_id[i] for i in group_ids) + kerf * (len(group_ids) - 1)


def _brute_force(stock_length, kerf, items):
    """枚举所有集合划分，返回 (最少根数, 字典序最小的排序分组列表)。"""
    ordered = sorted((gid, length) for gid, length in items)
    ids = [gid for gid, _ in ordered]
    length_by_id = dict(ordered)
    n = len(ids)

    best = None  # (根数, 排序后的组元组列表)

    def feasible(group):
        return _occupied(group, length_by_id, kerf) <= stock_length

    # 用受限增长串枚举全部集合划分：bins 为当前各箱的 id 元组。
    def recurse(i, bins):
        nonlocal best
        if i == n:
            groups = tuple(sorted(bins))
            if best is None or (len(groups), groups) < (len(best), best):
                best = groups
            return
        gid = ids[i]
        seen_sizes = set()
        for j in range(len(bins)):
            candidate = tuple(sorted(bins[j] + (gid,)))
            if candidate in seen_sizes or not feasible(candidate):
                continue
            seen_sizes.add(candidate)
            new_bins = bins[:j] + (candidate,) + bins[j + 1 :]
            recurse(i + 1, new_bins)
        # 新开一根（单件一定不超长，因为输入已过滤超长件）。
        recurse(i + 1, bins + ((gid,),))

    recurse(0, ())
    return best


def _run(stock_length, kerf, items):
    result = plan(stock_length, kerf, items)
    length_by_id = dict(items)

    # 每组占用/余料正确且不超长。
    for bar in result:
        assert bar["item_ids"] == sorted(bar["item_ids"])
        occupied = _occupied(bar["item_ids"], length_by_id, kerf)
        assert bar["occupied_length"] == occupied
        assert bar["remaining_length"] == stock_length - occupied
        assert occupied <= stock_length
        assert bar["remaining_length"] >= 0

    # 每件恰好覆盖一次。
    flat = [gid for bar in result for gid in bar["item_ids"]]
    assert sorted(flat) == sorted(length_by_id)
    assert len(flat) == len(set(flat)) == len(items)

    # 组列表按 id 列表字典序排列。
    group_lists = [bar["item_ids"] for bar in result]
    assert group_lists == sorted(group_lists)

    return group_lists


def test_basic_two_bars():
    bars = _run(
        6000,
        3,
        [("A", 3000), ("B", 2000), ("C", 2500), ("D", 1000)],
    )
    assert len(bars) == 2
    # ("A",) 是 ("A","B") 的前缀，标准字典序下 ("A",) 更小，
    # 且 B+C+D=5506<=6000 可行，故最优字典序方案把 A 单独成组。
    assert bars == [["A"], ["B", "C", "D"]]


def test_single_item_no_kerf_charge():
    result = plan(100, 5, [("X", 100)])
    assert result == [
        {"item_ids": ["X"], "occupied_length": 100, "remaining_length": 0}
    ]


def test_kerf_forces_separate_bars():
    # 两根 5：合占 5+5+1=11 > 10，必须分两根。
    bars = _run(10, 1, [("p", 5), ("q", 5)])
    assert bars == [["p"], ["q"]]


def test_zero_kerf_packs_tight():
    # 三个 5、容量 10：2 根方案有三组分法；("p",) 为前缀最小。
    bars = _run(10, 0, [("p", 5), ("q", 5), ("r", 5)])
    assert bars == [["p"], ["q", "r"]]


def test_tiebreak_prefers_smallest_tuple():
    # a,b=3，c,d=2，容量 5：两根方案有
    #   [a,c]+[b,d] 与 [a,d]+[b,c]（3+2、3+2 均可行），
    # 比较首组元组：(a,c) < (a,d)，取前者。
    bars = _run(5, 0, [("a", 3), ("b", 3), ("c", 2), ("d", 2)])
    assert bars == [["a", "c"], ["b", "d"]]


def test_input_ids_need_not_be_sorted():
    # 同为 2 根的方案：(a,b)+(m,z)、(a,m)+(b,z)、(a,z)+(b,m)，取首组最小者。
    bars = _run(10, 0, [("z", 6), ("a", 4), ("m", 4), ("b", 6)])
    assert bars == [["a", "b"], ["m", "z"]]


def test_all_items_separate_when_too_big_to_pair():
    bars = _run(5, 0, [("1", 3), ("2", 3), ("3", 3)])
    assert bars == [["1"], ["2"], ["3"]]


def test_random_small_instances_match_brute_force():
    rng = random.Random(20260924)
    for seed_case in range(300):
        n = rng.randint(1, 7)
        stock = rng.randint(5, 12)
        kerf = rng.randint(0, 2)
        ids = [f"i{i}" for i in range(n)]
        # 长度 1..stock，保证无超长单件。
        items = [(gid, rng.randint(1, stock)) for gid in ids]

        got = _run(stock, kerf, items)
        expected = _brute_force(stock, kerf, items)
        expected_lists = [list(group) for group in expected]
        assert got == expected_lists, (stock, kerf, items, got, expected_lists)


def test_fourteen_items_performance_and_coverage():
    rng = random.Random(42)
    items = [(f"ID-{i:02d}", rng.randint(50, 400)) for i in range(14)]
    start = time.perf_counter()
    result = plan(1000, 3, items)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    _run(1000, 3, items)  # 覆盖与排序断言

    # 占用总量 = 长度之和 +(件数-根数)*锯缝（锯缝总数与组数一致）。
    total_length = sum(length for _, length in items)
    occupied = sum(bar["occupied_length"] for bar in result)
    assert occupied == total_length + 3 * (14 - len(result))


def test_empty_items_returns_empty():
    # validation 层会拒绝空 items；核心函数本身应返回空方案。
    assert plan(100, 0, []) == []


def test_string_id_ordering_is_unicode_lexicographic():
    # 大写字母码位小于小写：B < a。两根方案中 (B,a)+(c,d) 的首组最小。
    bars = _run(10, 0, [("a", 6), ("B", 4), ("c", 4), ("d", 6)])
    assert bars == [["B", "a"], ["c", "d"]]

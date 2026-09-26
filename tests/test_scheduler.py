"""scheduler 单元测试，并用独立实现的暴力枚举对拍。"""

from __future__ import annotations

import random
import time
from itertools import permutations

from app.scheduler import schedule


def _brute_force(bars, jobs, initial_blade, changeover):
    """独立实现：枚举全部排列，按 (最大逾期, 总逾期, 索引序列) 取最小。"""
    n = len(jobs)
    best_key = None
    best_order = None
    best_detail = None
    for order in permutations(range(n)):
        prev_finish = 0
        prev_blade = initial_blade
        entries = []
        max_tard = 0
        total_tard = 0
        for index in order:
            duration, release, due, blade = jobs[index]
            co = changeover if blade != prev_blade else 0
            start = max(prev_finish + co, release)
            finish = start + duration
            tard = max(0, finish - due)
            entries.append((index, co, start, finish, tard))
            max_tard = max(max_tard, tard)
            total_tard += tard
            prev_finish = finish
            prev_blade = blade
        key = (max_tard, total_tard, order)
        if best_key is None or key < best_key:
            best_key = key
            best_order = order
            best_detail = entries
    return best_order, best_key, best_detail


def _check(bars, jobs, initial_blade, changeover):
    result = schedule(bars, jobs, initial_blade, changeover)
    order, key, detail = _brute_force(bars, jobs, initial_blade, changeover)

    n = len(jobs)
    assert result["bar_count"] == n
    assert [e["bar"] for e in result["schedule"]] == list(order)
    assert (
        result["max_tardiness"],
        result["total_tardiness"],
        tuple(e["bar"] for e in result["schedule"]),
    ) == key

    for entry, (index, co, start, finish, tard) in zip(result["schedule"], detail):
        assert entry == {
            "bar": index,
            "item_ids": list(bars[index]["item_ids"]),
            "changeover": co,
            "start": start,
            "finish": finish,
            "tardiness": tard,
        }

    assert result["makespan"] == result["schedule"][-1]["finish"]
    assert result["max_tardiness"] == max(e[4] for e in detail)
    return result


def _bar(item_ids):
    return {"item_ids": list(item_ids)}


def test_single_bar_with_initial_blade_changeover():
    # 初始刀具不同：首根先换刀（3），再与 release 取 max。
    result = _check(
        [_bar(["A"])],
        [(5, 2, 10, "X")],
        initial_blade="Y",
        changeover=3,
    )
    assert result["schedule"] == [
        {
            "bar": 0,
            "item_ids": ["A"],
            "changeover": 3,
            "start": 3,
            "finish": 8,
            "tardiness": 0,
        }
    ]
    assert result["max_tardiness"] == 0
    assert result["total_tardiness"] == 0
    assert result["makespan"] == 8


def test_release_greater_than_changeover_delays_start():
    # release(10) 晚于换刀完成时刻(3)，开工取 10。
    result = _check([_bar(["A"])], [(5, 10, 20, "X")], "Y", 3)
    assert result["schedule"][0]["start"] == 10
    assert result["schedule"][0]["finish"] == 15


def test_same_blade_no_changeover_lexicographic_tie():
    # 两根完全对称：指标相同，取索引序列字典序 [0,1]。
    result = _check(
        [_bar(["A"]), _bar(["B"])],
        [(5, 0, 5, "A"), (5, 0, 5, "A")],
        initial_blade="A",
        changeover=3,
    )
    entries = result["schedule"]
    assert [e["bar"] for e in entries] == [0, 1]
    assert entries[0] == {
        "bar": 0,
        "item_ids": ["A"],
        "changeover": 0,
        "start": 0,
        "finish": 5,
        "tardiness": 0,
    }
    assert entries[1] == {
        "bar": 1,
        "item_ids": ["B"],
        "changeover": 0,
        "start": 5,
        "finish": 10,
        "tardiness": 5,
    }
    assert result["max_tardiness"] == 5
    assert result["total_tardiness"] == 5


def test_release_date_idle_wait_dominates():
    # bar0 release=10；先做 bar1（0~3），再等 release 做 bar0，两根都不逾期。
    result = _check(
        [_bar(["A"]), _bar(["B"])],
        [(2, 10, 12, "A"), (3, 0, 3, "A")],
        initial_blade="A",
        changeover=0,
    )
    assert [e["bar"] for e in result["schedule"]] == [1, 0]
    first, second = result["schedule"]
    assert (first["start"], first["finish"], first["tardiness"]) == (0, 3, 0)
    assert (second["start"], second["finish"], second["tardiness"]) == (10, 12, 0)
    assert result["max_tardiness"] == 0
    assert result["makespan"] == 12


def test_changeover_inserted_between_different_blades():
    # 初始刀具 A；首根 A 不换刀，B 换刀 4，A 再换刀 4。
    result = _check(
        [_bar(["A1", "A2"]), _bar(["B"]), _bar(["A3"])],
        [(3, 0, 3, "A"), (2, 0, 100, "B"), (1, 0, 100, "A")],
        initial_blade="A",
        changeover=4,
    )
    assert [e["bar"] for e in result["schedule"]] == [0, 1, 2]
    assert [e["changeover"] for e in result["schedule"]] == [0, 4, 4]
    assert [e["start"] for e in result["schedule"]] == [0, 7, 13]
    assert [e["finish"] for e in result["schedule"]] == [3, 9, 14]
    assert result["schedule"][0]["item_ids"] == ["A1", "A2"]


def test_total_tardiness_breaks_max_tardiness_tie():
    # bar0: d2 r1 due7 A；bar1: d2 r4 due7 B；bar2: d5 r2 due11 B；
    # bar3: d3 r4 due0 B；初始 A，换刀 1。
    # 最优最大逾期 7 有多个排列：(0,3,1,2) 总逾期 12，(0,3,2,1) 总逾期 15，
    # 二级准则应选出总逾期更小的 (0,3,1,2)。
    jobs = [
        (2, 1, 7, "A"),
        (2, 4, 7, "B"),
        (5, 2, 11, "B"),
        (3, 4, 0, "B"),
    ]
    result = _check([_bar(["a"]), _bar(["b"]), _bar(["c"]), _bar(["d"])], jobs, "A", 1)
    assert [e["bar"] for e in result["schedule"]] == [0, 3, 1, 2]
    assert [e["changeover"] for e in result["schedule"]] == [0, 1, 0, 0]
    assert [e["start"] for e in result["schedule"]] == [1, 4, 7, 9]
    assert [e["finish"] for e in result["schedule"]] == [3, 7, 9, 14]
    assert [e["tardiness"] for e in result["schedule"]] == [0, 7, 2, 3]
    assert result["max_tardiness"] == 7
    assert result["total_tardiness"] == 12
    assert result["makespan"] == 14


def test_random_small_instances_match_brute_force():
    rng = random.Random(20260925)
    blades = ["A", "B", "C"]
    for _ in range(200):
        n = rng.randint(1, 7)
        bars = [_bar([f"i{j}"]) for j in range(n)]
        jobs = [
            (
                rng.randint(1, 8),          # duration
                rng.randint(0, 8),          # release
                rng.randint(0, 20),         # due
                rng.choice(blades),         # blade
            )
            for _ in range(n)
        ]
        initial_blade = rng.choice(blades)
        changeover = rng.randint(0, 5)
        _check(bars, jobs, initial_blade, changeover)


def test_nine_bars_performance():
    rng = random.Random(7)
    n = 9
    bars = [_bar([f"ID-{i:02d}"]) for i in range(n)]
    jobs = [
        (
            rng.randint(1, 20),
            rng.randint(0, 15),
            rng.randint(0, 120),
            rng.choice(["X", "Y"]),
        )
        for _ in range(n)
    ]
    start = time.perf_counter()
    result = schedule(bars, jobs, "X", 5)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    assert len(result["schedule"]) == 9
    assert [sorted(e["bar"] for e in result["schedule"])][0] == list(range(9))

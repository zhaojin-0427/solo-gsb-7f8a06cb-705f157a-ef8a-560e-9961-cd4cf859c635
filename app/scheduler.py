"""单台锯床排序：为 1～9 根待加工原料安排加工顺序。

时间规则（顺序中第 k 根，k 从 0 起）：

- 换刀耗时：首根与初始刀具 initial_blade 比较；其后与前一根的刀具比较。
  刀具相同为 0，不同为 changeover；
- 开工：start_0 = max(0 + 换刀耗时_0, release_0)（首根前的完工时刻为 0）；
  start_k = max(finish_{k-1} + 换刀耗时_k, release_k)；
- 完工：finish_k = start_k + duration_k；
- 单根逾期：tardiness_k = max(0, finish_k - due_k)。

优化目标按以下优先级取最小：

1. 最大逾期 max(tardiness)；
2. 总逾期 sum(tardiness)；
3. bar 索引序列的字典序。

根数上限 9，直接枚举全部排列（9! = 362880）取精确最优解。
"""

from __future__ import annotations

from itertools import permutations
from typing import Any

# 接口限定每次最多 9 根；枚举复杂度为 O(n!·n)。
MAX_BARS = 9


def schedule(
    bars: list[dict[str, Any]],
    jobs: list[tuple[int, int, int, str]],
    initial_blade: str,
    changeover: int,
) -> dict[str, object]:
    """计算单台锯床的最优加工顺序。

    参数:
        bars: /plans 返回的 bars（至少含非空 ``item_ids``），长度 1～9。
        jobs: 与 bars 等长，每项为 (duration, release, due, blade)；
              duration 为正整数，release/due 为非负整数，blade 为非空字符串。
        initial_blade: 初始刀具（非空字符串）。
        changeover: 换刀耗时（非负整数）。

    返回:
        含 ``schedule``（按加工顺序排列，每根给出原索引、成品 id、
        换刀耗时、开工、完工、逾期）及总体指标的字典。
    """
    n = len(jobs)
    if n == 0:
        return {
            "bar_count": 0,
            "schedule": [],
            "max_tardiness": 0,
            "total_tardiness": 0,
            "makespan": 0,
        }

    # 评分元组把 bar 索引序列纳入末位：排列不同则索引序列不同，
    # 三级键严格实现“最大逾期→总逾期→字典序”的比较规则。
    best_order = min(
        permutations(range(n)),
        key=lambda order: _score(order, jobs, initial_blade, changeover),
    )

    entries: list[dict[str, object]] = []
    prev_finish = 0
    prev_blade = initial_blade
    max_tardiness = 0
    total_tardiness = 0
    for index in best_order:
        duration, release, due, blade = jobs[index]
        co = changeover if blade != prev_blade else 0
        start = max(prev_finish + co, release)
        finish = start + duration
        tardiness = max(0, finish - due)

        max_tardiness = max(max_tardiness, tardiness)
        total_tardiness += tardiness
        entries.append(
            {
                "bar": index,
                "item_ids": list(bars[index]["item_ids"]),
                "changeover": co,
                "start": start,
                "finish": finish,
                "tardiness": tardiness,
            }
        )
        prev_finish = finish
        prev_blade = blade

    return {
        "bar_count": n,
        "schedule": entries,
        "max_tardiness": max_tardiness,
        "total_tardiness": total_tardiness,
        "makespan": prev_finish,
    }


def _score(
    order: tuple[int, ...],
    jobs: list[tuple[int, int, int, str]],
    initial_blade: str,
    changeover: int,
) -> tuple[int, int, tuple[int, ...]]:
    """按给定顺序模拟，返回 (最大逾期, 总逾期, bar 索引序列)。"""
    prev_finish = 0
    prev_blade = initial_blade
    max_tardiness = 0
    total_tardiness = 0
    for index in order:
        duration, release, due, blade = jobs[index]
        co = changeover if blade != prev_blade else 0
        start = max(prev_finish + co, release)
        finish = start + duration
        tardiness = max(0, finish - due)

        if tardiness > max_tardiness:
            max_tardiness = tardiness
        total_tardiness += tardiness
        prev_finish = finish
        prev_blade = blade
    return max_tardiness, total_tardiness, order

"""定尺线材开料：一维下料（带锯缝）的精确最优求解。

每件成品在一根原料上的占用长度为：

    重量 w_i = 成品长度 l_i + 锯缝宽度 k

一根原料上 n 件的总占用为 sum(w_i) - k（等价于 sum(l_i) + (n-1)*k）。
容量 C = 原料长度 + 锯缝宽度，问题化为一维装箱问题。

件数最多 14 件，用子集 DP 求全局最少原料根数：

    dp[S] = 覆盖集合 S 所需的最少根数

再配合“逐组贪心选最小 id 元组 + 可行性判定”，在所有最优方案中选出
排序后分组列表字典序最小的方案。
"""

from __future__ import annotations

# 接口限定每件请求最多 14 件；DP 复杂度约为 O(3^n)。
MAX_ITEMS = 14


def plan(stock_length: int, kerf: int, items: list[tuple[str, int]]):
    """计算开料方案。

    参数:
        stock_length: 原料（定尺）长度，正整数。
        kerf: 锯缝宽度，非负整数。
        items: 元素为 (id, 长度) 的列表，长度为正整数，id 唯一；
               单件长度不得超过原料长度。

    返回:
        list[dict]，每组包含 ``item_ids``（升序）、``occupied_length``
        和 ``remaining_length``。组列表本身按 id 列表字典序排列，
        且在所有最优方案中字典序最小。
    """
    if not items:
        return []

    # 统一按 id 升序处理，便于输出排序与字典序比较。
    ordered = sorted(items, key=lambda pair: pair[0])
    ids = [pair[0] for pair in ordered]
    lengths = [pair[1] for pair in ordered]

    # 每件增加一个锯缝宽度；容量相应加一个锯缝宽度，
    # 则“n 件总长 +(n-1) 锯缝 <= 原料长度”等价于“重量和 <= 容量”。
    weights = [length + kerf for length in lengths]
    capacity = stock_length + kerf

    n = len(ids)
    full = (1 << n) - 1

    # 预计算每个子集的重量和与可行性（不超长）。
    sum_w = [0] * (1 << n)
    feasible = [False] * (1 << n)
    for mask in range(1, 1 << n):
        low = mask & -mask
        bit = low.bit_length() - 1
        prev = mask ^ low
        total = sum_w[prev] + weights[bit]
        sum_w[mask] = total
        feasible[mask] = total <= capacity

    # dp[S]：恰好覆盖 S 的最少原料根数。
    # 枚举 S 的非空可行子集作为“最后一根”。
    INF = n + 1
    dp = [0] + [INF] * full
    for mask in range(1, full + 1):
        if feasible[mask]:
            dp[mask] = 1
            continue
        best = INF
        # 固定最低位必须在该组内，避免把同一根原料的内容重复枚举。
        anchor = mask & -mask
        rest = mask ^ anchor
        sub = rest
        while True:
            group = sub | anchor
            if feasible[group]:
                cand = dp[mask ^ group] + 1
                if cand < best:
                    best = cand
            if sub == 0:
                break
            sub = (sub - 1) & rest
        dp[mask] = best

    min_bars = dp[full]

    # 在所有恰好用 min_bars 根的方案中，构造排序后分组列表字典序最小者。
    # 逐组确定：每次在“剩余件可由剩余根数覆盖”的前提下，选择 id 元组
    # 字典序最小的可行组。可行性即 dp[剩余] <= 剩余根数。
    groups: list[list[str]] = []
    remaining_mask = full
    remaining_bars = min_bars
    while remaining_mask:
        anchor = remaining_mask & -remaining_mask
        rest = remaining_mask ^ anchor
        best_group_mask = None
        sub = rest
        while True:
            group_mask = sub | anchor
            leftover = remaining_mask ^ group_mask
            if feasible[group_mask] and dp[leftover] <= remaining_bars - 1:
                if best_group_mask is None or _mask_tuple(group_mask, ids) < _mask_tuple(
                    best_group_mask, ids
                ):
                    best_group_mask = group_mask
            if sub == 0:
                break
            sub = (sub - 1) & rest

        # 输入合法（每件均不超长）时一定存在方案，这里仅作防御性断言。
        assert best_group_mask is not None
        group_ids = [ids[i] for i in range(n) if best_group_mask & (1 << i)]
        groups.append(group_ids)
        remaining_mask ^= best_group_mask
        remaining_bars -= 1

    # 贪心构造天然递增，这里再排序一次以严格满足输出约定。
    groups.sort()

    length_by_id = dict(items)
    result = []
    for group_ids in groups:
        occupied = sum(length_by_id[gid] for gid in group_ids) + kerf * (
            len(group_ids) - 1
        )
        result.append(
            {
                "item_ids": group_ids,
                "occupied_length": occupied,
                "remaining_length": stock_length - occupied,
            }
        )
    return result


def _mask_tuple(mask: int, ids: list[str]) -> tuple[str, ...]:
    """返回子集（按位对应）内 id 升序组成的元组。"""
    return tuple(ids[i] for i in range(len(ids)) if mask & (1 << i))

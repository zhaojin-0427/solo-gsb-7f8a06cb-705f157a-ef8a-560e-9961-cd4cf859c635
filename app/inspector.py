"""成品检验：按 /plans 的 bars 逐根核对实测成品长度。

实测件没有标签，且**不跨根匹配**：bar i 上的标称成品（id、标称长度）
只能与 measurements[i] 中的实测长度一对一配对，配对条件为

    |实测长度 - 标称长度| <= tolerance

每根原料在所有可行配对方案中，依次优化：

1. 配对数最多；
2. 配对件的绝对偏差总和最小；
3. 仍并列时，取按 id 升序排列的 ``(id, 实测下标)`` 配对列表
   字典序最小者。

单根最多 14 件、全单实测最多 14 条，用“实测子集 DP”求精确最优解：
layers[i][mask] 表示处理第 i 件（按 id 升序）及其后各件、剩余可用实测
下标集合为 mask 时，最优的 (配对数, 绝对偏差和)。第 i 件要么缺件
（不用实测），要么与 mask 中任一容差内的实测配对。

DP 只确定 (配对数, 偏差和)；字典序最优方案由逐层贪心恢复：在仍能达到
DP 最优值的前提下优先配对当前 id（其配对元组一定小于任何以更大 id
开头的方案），并取下标最小的可行实测。
"""

from __future__ import annotations

from typing import Any

# 接口限定成品件数与全单实测条数均不超过 14。
MAX_ITEMS = 14


def inspect(
    bars: list[dict[str, Any]],
    items: list[tuple[str, int]],
    measurements: list[list[int]],
    tolerance: int,
) -> dict[str, object]:
    """逐根核对成品与实测长度。

    参数:
        bars: /plans 返回的 bars（至少含非空 ``item_ids``），
              每个 item id 在所有 bars 中恰好出现一次。
        items: 元素为 (id, 标称长度) 的列表，与 bars 覆盖同一组 id。
        measurements: 与 bars 等长；measurements[i] 为第 i 根的实测
                      长度数组（正整数，可为空）。
        tolerance: 非负整数容差；长度差绝对值不超过它才可配对。

    返回:
        含 ``inspections``（每根的配对、缺件、余件与合格标志）及总体
        ``qualified`` 的字典。配对偏差为有符号值：实测长度 − 标称长度。
    """
    length_by_id = dict(items)
    inspections: list[dict[str, object]] = []
    all_qualified = True

    for index, bar in enumerate(bars):
        ids = sorted(bar["item_ids"])
        nominal = [length_by_id[gid] for gid in ids]
        observed = measurements[index]
        pairs, missing_ids, surplus = _match_bar(ids, nominal, observed, tolerance)
        qualified = not missing_ids and not surplus
        all_qualified = all_qualified and qualified
        inspections.append(
            {
                "bar": index,
                "pairs": pairs,
                "missing_ids": missing_ids,
                "surplus_measurements": surplus,
                "qualified": qualified,
            }
        )

    return {
        "bar_count": len(bars),
        "inspections": inspections,
        "qualified": all_qualified,
    }


def _match_bar(
    ids: list[str],
    nominal: list[int],
    observed: list[int],
    tolerance: int,
) -> tuple[list[dict[str, object]], list[str], list[int]]:
    """求单根的最优配对，返回 (配对列表, 缺件 id 列表, 余件下标列表)。"""
    m = len(ids)
    k = len(observed)
    size = 1 << k
    full = size - 1

    # layers[i][mask]：处理第 i..m-1 件、可用实测集合为 mask 时的
    # 最优 (配对数, 绝对偏差和)。全部缺件/余件始终可行，故不会出现 None。
    # layers[m] 为基底层：再无标称件，配对数与偏差均为 0。
    layers: list[list[tuple[int, int]]] = [[(0, 0)] * size]
    for i in range(m - 1, -1, -1):
        length = nominal[i]
        nxt = layers[-1]
        cur: list[tuple[int, int]] = [(0, 0)] * size
        for mask in range(size):
            # 选择一：本件缺件，不消耗实测。
            best_count, best_cost = nxt[mask]
            # 选择二：与 mask 中容差范围内的某条实测配对。
            remaining = mask
            while remaining:
                low = remaining & -remaining
                j = low.bit_length() - 1
                diff = abs(observed[j] - length)
                if diff <= tolerance:
                    tail_count, tail_cost = nxt[mask ^ low]
                    # 先比配对数（越大越好），再比偏差和（越小越好）。
                    if (
                        tail_count + 1 > best_count
                        or (tail_count + 1 == best_count and tail_cost + diff < best_cost)
                    ):
                        best_count, best_cost = tail_count + 1, tail_cost + diff
                remaining ^= low
            cur[mask] = (best_count, best_cost)
        layers.append(cur)
    # 追加顺序为基底、m-1、…、0；反转后 layers[i] 即第 i 件层。
    layers.reverse()

    # 逐层贪心恢复字典序最小的最优方案。
    # 每件按实测下标从小到大尝试：首个仍能达到该状态 DP 最优值的配对
    # 即为字典序最优选择（元组首位 id 已固定为当前 id，下标越小越小）；
    # 不存在则本件缺件。优先配对还因为 (当前 id, j) 必然小于任何以更大
    # id 开头的缺件方案。
    pairs: list[dict[str, object]] = []
    missing_ids: list[str] = []
    mask = full
    for i in range(m):
        length = nominal[i]
        opt_count, opt_cost = layers[i][mask]
        chosen: int | None = None
        remaining = mask
        while remaining:
            low = remaining & -remaining
            j = low.bit_length() - 1
            diff = abs(observed[j] - length)
            if diff <= tolerance:
                tail_count, tail_cost = layers[i + 1][mask ^ low]
                if tail_count + 1 == opt_count and tail_cost + diff == opt_cost:
                    chosen = j
                    break
            remaining ^= low

        if chosen is None:
            missing_ids.append(ids[i])
            continue
        pairs.append(
            {
                "id": ids[i],
                "measurement_index": chosen,
                # 有符号偏差：实测 − 标称（实测偏短为负）。
                "deviation": observed[chosen] - length,
            }
        )
        mask ^= 1 << chosen

    surplus = [j for j in range(k) if mask & (1 << j)]
    return pairs, missing_ids, surplus

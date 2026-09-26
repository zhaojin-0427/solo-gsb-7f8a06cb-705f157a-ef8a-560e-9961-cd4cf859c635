"""成品检验：按 /plans 的 bars 核对无标签实测件。

每根原料独立核对（实测件不跨根匹配）：在该根的计划成品与实测长度之间
建立一对一配对，仅当 |实测 − 计划| <= tolerance 时允许配对。

每根的配对目标按优先级为：

1. 配对数最大；
2. 绝对偏差总和最小；
3. 按 id 升序排列的 (id, 实测下标) 配对列表字典序最小。

单根内成品数与实测条数都不超过 14，用“按 id 升序逐件决策 + 实测占用
掩码”的子集 DP 求解：同一掩码下各可行部分解的配对数相同（等于掩码
位数），故 (偏差和, 配对列表) 的比较在逐件扩展时保持前缀一致，每个
掩码只需保留最优的一份部分解。
"""

from __future__ import annotations

# 全单实测条数上限（与成品件数上限一致）。
MAX_MEASUREMENTS = 14


def inspect(
    items: list[tuple[str, int]],
    bars: list[list[str]],
    measurements: list[list[int]],
    tolerance: int,
) -> dict[str, object]:
    """核对一单成品，返回逐根配对结果与总体合格标记。

    参数:
        items: [(id, 计划长度)]，id 唯一，长度为正整数。
        bars: 每根原料上的成品 id 列表（对应 /plans 的 item_ids）；
              每个 item id 在全体 bars 中恰好出现一次。
        measurements: 与 bars 等长；每根为该根的实测长度列表（可为空），
              全单总条数不超过 MAX_MEASUREMENTS。
        tolerance: 长度公差，非负整数。

    返回:
        含 ``bar_count``、``qualified``（各根缺件与余件均为空才为 True）
        以及逐根明细（``pairs``/``missing``/``leftover``）的字典。
    """
    length_by_id = dict(items)
    results: list[dict[str, object]] = []
    for item_ids, measured in zip(bars, measurements):
        planned = sorted((item_id, length_by_id[item_id]) for item_id in item_ids)
        pairs, missing, leftover = _match_bar(planned, measured, tolerance)
        results.append(
            {
                "pairs": [
                    {
                        "id": item_id,
                        "measurement": index,
                        # 有符号偏差：正表示实测偏长，负表示偏短。
                        "deviation": measured[index] - length_by_id[item_id],
                    }
                    for item_id, index in pairs
                ],
                "missing": missing,
                "leftover": leftover,
            }
        )
    qualified = all(not bar["missing"] and not bar["leftover"] for bar in results)
    return {"bar_count": len(results), "qualified": qualified, "bars": results}


def _match_bar(
    planned: list[tuple[str, int]],
    measured: list[int],
    tolerance: int,
) -> tuple[list[tuple[str, int]], list[str], list[int]]:
    """求单根原料的最优配对。

    参数:
        planned: 按 id 升序的 [(id, 计划长度)]。
        measured: 该根的实测长度列表（下标即从 0 起的实测编号）。
        tolerance: 允许配对的最大绝对长度差。

    返回:
        (pairs, missing, leftover)：pairs 为按 id 升序的 (id, 实测下标)，
        missing 为未配对成品 id（升序），leftover 为未使用实测下标（升序）。
    """
    # dp[mask] = (绝对偏差和, 配对列表元组)：已处理的成品中，占用 mask 内
    # 实测条目的最优部分解。同一 mask 的配对数相同（= 掩码位数），逐件
    # 扩展时字典序前缀一致，故每个 mask 只保留 (偏差和, 配对列表) 最小者。
    dp: dict[int, tuple[int, tuple[tuple[str, int], ...]]] = {0: (0, ())}
    for item_id, length in planned:
        ndp = dict(dp)  # 情形一：本件不配对（计入缺件）。
        for mask, (deviation, pairs) in dp.items():
            for index, got in enumerate(measured):
                bit = 1 << index
                if mask & bit:
                    continue
                delta = abs(got - length)
                if delta > tolerance:
                    continue
                candidate = (deviation + delta, pairs + ((item_id, index),))
                nmask = mask | bit
                if nmask not in ndp or candidate < ndp[nmask]:
                    ndp[nmask] = candidate
        dp = ndp

    # 配对数 = mask 位数：先取最大，再取 (偏差和, 配对列表) 最小者。
    _, (_, best_pairs) = min(dp.items(), key=lambda kv: (-kv[0].bit_count(), kv[1]))

    matched_ids = {item_id for item_id, _ in best_pairs}
    used = {index for _, index in best_pairs}
    missing = [item_id for item_id, _ in planned if item_id not in matched_ids]
    leftover = [index for index in range(len(measured)) if index not in used]
    return list(best_pairs), missing, leftover

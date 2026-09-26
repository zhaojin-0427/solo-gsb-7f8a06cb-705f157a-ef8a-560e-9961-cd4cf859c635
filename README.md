# 定尺线材开料 API（Python / FastAPI）

服务提供两个接口：

- `POST /plans`：给定定尺原料长度、锯缝宽度和 1～14 件成品（唯一字符串
  id、正整数长度），计算覆盖每件成品**恰好一次**且每根原料不超长的前提下，
  **全局最少原料根数**的下料方案。
- `POST /schedules`：为 `/plans` 返回的 **1～9 根** bars，安排**单台锯床**
  的加工顺序，在给定每件加工时长、释放时刻、交期与刀具的条件下，最小化
  **最大逾期**。

一根原料上排 `n` 件成品时，占用长度为：

```
成品长度之和 + (n - 1) × 锯缝宽度
```

由于件数上限仅 14，服务使用**子集动态规划**求精确最优解（非启发式近似），
并在存在多个最优方案时，返回“排序后分组列表字典序最小”的那个：

- 每根原料内成品 id 按**升序**排列；
- 各组按其 id 列表的**字典序**排列（Python/Unicode 字符串比较，
  且列表比较遵守标准规则：一个列表是另一个列表的前缀时，更短者更小）；
- 若多个方案根数相同，取分组列表字典序最小者。

## 目录结构

```
.
├── app/
│   ├── main.py        # FastAPI 入口：POST /plans、POST /schedules、GET /health
│   ├── planner.py     # 子集 DP 精确求解 + 字典序最优方案构造
│   ├── scheduler.py   # 排列枚举求单台锯床最优加工顺序（1～9 根）
│   └── validation.py  # 请求体严格校验（整数/结构/重复 id/超长单件）
├── tests/             # pytest 单元与接口测试
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 用 Docker Compose 启动

```bash
docker compose up --build
```

启动后服务监听 **http://localhost:8000**：

- 接口：`POST http://localhost:8000/plans`
- 接口：`POST http://localhost:8000/schedules`
- 健康检查：`GET http://localhost:8000/health`
- 交互式文档（Swagger UI）：<http://localhost:8000/docs>

### 调用示例

```bash
curl -s -X POST http://localhost:8000/plans \
  -H "Content-Type: application/json" \
  -d '{
    "stock_length": 6000,
    "kerf": 3,
    "items": [
      {"id": "A", "length": 3000},
      {"id": "B", "length": 2000},
      {"id": "C", "length": 2500},
      {"id": "D", "length": 1000}
    ]
  }'
```

响应：

```json
{
  "stock_length": 6000,
  "kerf": 3,
  "bar_count": 2,
  "bars": [
    {"item_ids": ["A"], "occupied_length": 3000, "remaining_length": 3000},
    {"item_ids": ["B", "C", "D"], "occupied_length": 5506, "remaining_length": 494}
  ]
}
```

本例 2 根原料即可覆盖全部成品，且存在多个 2 根方案，例如
`["A"]+["B","C","D"]`、`["A","B"]+["C","D"]`、`["A","D"]+["B","C"]`。
按字符串列表的标准字典序，首组 `("A",)` 是 `("A","B")`、`("A","D")` 的
**前缀，更短者更小**，因此最优方案为把 A 单独放在一根上。

## POST /schedules：单台锯床排产

把 `/plans` 返回的 `bars`（取其中 1～9 根）与等长的 `jobs` 一并提交，
`jobs[i]` 描述 `bars[i]` 的加工参数：正整数 `duration`（加工时长）、
非负整数 `release`（最早可开工时刻）、非负整数 `due`（交期）、
非空字符串 `blade`（所需刀具）。另外提交非空字符串 `initial_blade`
（初始刀具）与非负整数 `changeover`（换刀耗时）。

时间规则：

- **换刀耗时**：刀具不同计 `changeover`，相同计 0；首根与
  `initial_blade` 比较，其后与前一根的刀具比较；
- **开工** = max(前一根完工 + 本根换刀耗时, 本根 release)；
  首根之前的“完工时刻”为 0；
- **完工** = 开工 + duration；
- **单根逾期** = max(0, 完工 − due)。

优化目标依次为：**最大逾期最小 → 总逾期最小 → bar 索引序列字典序最小**。
根数上限仅 9，服务枚举全部排列（最多 9! = 362880 个）取精确最优解。

### 调用示例（localhost:8000）

```bash
curl -s -X POST http://localhost:8000/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "initial_blade": "A",
    "changeover": 1,
    "bars": [
      {"item_ids": ["A"]},
      {"item_ids": ["B", "C", "D"]}
    ],
    "jobs": [
      {"duration": 3, "release": 0, "due": 3,  "blade": "A"},
      {"duration": 6, "release": 0, "due": 20, "blade": "B"}
    ]
  }'
```

响应（`bar` 为该根在请求 `bars` 中的**下标，从 0 起**）：

```json
{
  "initial_blade": "A",
  "changeover": 1,
  "bar_count": 2,
  "schedule": [
    {"bar": 0, "item_ids": ["A"], "changeover": 0, "start": 0, "finish": 3, "tardiness": 0},
    {"bar": 1, "item_ids": ["B", "C", "D"], "changeover": 1, "start": 4, "finish": 10, "tardiness": 0}
  ],
  "max_tardiness": 0,
  "total_tardiness": 0,
  "makespan": 10
}
```

首根刀具与初始刀具同为 A，换刀耗时为 0，`start = max(0+0, 0) = 0`；
第二根换刀到 B，换刀耗时为 1，`start = max(3+1, 0) = 4`。

### 不用 Docker 的本地运行方式

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 请求字段

### POST /plans

| 字段           | 类型                | 约束                                   |
| -------------- | ------------------- | -------------------------------------- |
| `stock_length` | 整数                | 必填，正整数，原料（定尺）长度         |
| `kerf`         | 整数                | 必填，非负整数，锯缝宽度（可为 0）     |
| `items`        | 数组（1～14 个元素）| 必填                                   |
| `items[].id`   | 字符串              | 必填，全局唯一                         |
| `items[].length` | 整数              | 必填，正整数，且不得超过原料长度       |

### POST /schedules

| 字段                    | 类型                 | 约束                                        |
| ----------------------- | -------------------- | ------------------------------------------- |
| `initial_blade`         | 字符串               | 必填，非空，初始刀具                        |
| `changeover`            | 整数                 | 必填，非负，换刀耗时                        |
| `bars`                  | 数组（1～9 个元素）  | 必填，可直接使用 `/plans` 返回的 `bars`     |
| `bars[].item_ids`       | 字符串数组           | 必填，非空，该根原料上的成品 id             |
| `bars[].occupied_length` | 整数                | 可选（`/plans` 会返回），非负               |
| `bars[].remaining_length` | 整数               | 可选（`/plans` 会返回），非负               |
| `jobs`                  | 数组                 | 必填，与 `bars` **等长**，`jobs[i]` 对应 `bars[i]` |
| `jobs[].duration`       | 整数                 | 必填，正整数，加工时长                      |
| `jobs[].release`        | 整数                 | 必填，非负，最早可开工时刻                  |
| `jobs[].due`            | 整数                 | 必填，非负，交期                            |
| `jobs[].blade`          | 字符串               | 必填，非空，所需刀具                        |

只接受上表中的字段；任何多余字段、缺失字段都会报错。整数必须是 JSON 真正的
整数：`5.0`、`"5"`、`true` 均视为**非法整数**。

## 响应字段

### POST /plans

| 字段                | 说明                                       |
| ------------------- | ------------------------------------------ |
| `bar_count`         | 使用的原料根数（全局最少）                 |
| `bars[].item_ids`   | 该根原料上的成品 id，组内升序              |
| `bars[].occupied_length` | 该根原料的占用长度 = 长度之和 +(n−1)×锯缝 |
| `bars[].remaining_length` | 余料 = 原料长度 − 占用长度               |

### POST /schedules

| 字段                       | 说明                                              |
| -------------------------- | ------------------------------------------------- |
| `bar_count`                | 参与排产的根数                                     |
| `schedule[]`               | 按**加工顺序**排列的每根明细                       |
| `schedule[].bar`           | 该根在请求 `bars` 中的下标（**从 0 起**）          |
| `schedule[].item_ids`      | 成品 id（原样取自对应 bar）                        |
| `schedule[].changeover`    | 本根开工前的换刀耗时（刀具不同为 `changeover`，否则 0；首根对照初始刀具） |
| `schedule[].start`         | 开工时刻 = max(上一根完工 + 换刀耗时, release)     |
| `schedule[].finish`        | 完工时刻 = 开工 + duration                        |
| `schedule[].tardiness`     | 逾期 = max(0, 完工 − due)                         |
| `max_tardiness`            | 总体最大逾期（首要优化目标）                       |
| `total_tardiness`          | 总体总逾期（并列时的次要目标）                     |
| `makespan`                 | 全部完工时刻（最后一根的 `finish`）                |

并列规则：最大逾期相同时取**总逾期**更小的；仍相同取 bar 索引序列
（即 `schedule[].bar` 依次组成的序列）**字典序最小**的。

## 错误响应

非法请求统一返回 **HTTP 422**，形如 `{"detail": "错误原因"}`。

`POST /plans` 包括：

- 某件成品长度超过原料长度（超长单件，无论锯缝多少都不可能装入）；
- 成品 id 重复；
- 非整数 / 非正整数（`stock_length`、`items[].length`），负锯缝；
- 件数不在 1～14 之间；id 不是字符串；请求体不是合法 JSON 对象；
- 缺少必填字段或出现未声明字段。

`POST /schedules` 包括：

- `bars` 根数不在 1～9 之间，或 `jobs` 与 `bars` 不等长；
- `bars[].item_ids` 缺失、不是非空字符串数组，bar/job 不是对象；
- `jobs[].duration` 非正整数，`release`/`due`/`changeover` 为负数
  或非整数，`blade`/`initial_blade` 为空或不是字符串；
- 请求体不是合法 JSON 对象、不是对象（如 JSON 数组）；
- 缺少必填字段或出现未声明字段。

## 运行测试

```bash
pip install -r requirements.txt pytest
pytest -q
```

## 算法说明

令每件“重量”为 `长度 + kerf`，容量为 `原料长度 + kerf`，则

```
sum(长度) + (n-1)·kerf <= 原料长度  ⇔  sum(长度 + kerf) <= 原料长度 + kerf
```

问题等价于一维装箱。对 14 件的全部子集（最多 2^14 = 16384 个）做 DP：

```
dp[S] = 覆盖集合 S 的最少原料根数
      = 1 + min(dp[S \\ G])，其中 G 是 S 的非空可行子集
```

得到全局最少根数后，逐根贪心确定分组：每一步在“剩余件仍能由剩余根数
覆盖”（由 dp 表判定）的所有可行组中，选 id 元组字典序最小的组。
由此得到的排序分组列表，是所有最优方案中字典序最小的。

### 单台锯床排序（POST /schedules）

这是带释放时刻、顺序相关换刀耗时的单机排序问题（一般情形为 NP-hard）。
由于根数上限只有 9，直接枚举全部 n! 个排列，按排列模拟计算各根的
换刀耗时、开工、完工与逾期，再以

```
(最大逾期, 总逾期, bar 索引序列)
```

三元组取字典序最小的排列。三级键保证并列时先比总逾期、再比索引序列
（索引序列相等等价于同一排列）。9 根时枚举上限 9! = 362880 个排列，
每个排列 O(n) 模拟，毫秒级完成。

"""POST /inspections 接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(body):
    return client.post("/inspections", json=body)


def _body(**overrides):
    body = {
        "items": [
            {"id": "A", "length": 100},
            {"id": "B", "length": 200},
        ],
        "bars": [{"item_ids": ["A"]}, {"item_ids": ["B"]}],
        "measurements": [[100], [200]],
        "tolerance": 5,
    }
    body.update(overrides)
    return body


def test_valid_all_matched_qualified():
    resp = post(_body(measurements=[[101], [197]]))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "tolerance": 5,
        "bar_count": 2,
        "qualified": True,
        "bars": [
            {
                "pairs": [{"id": "A", "measurement": 0, "deviation": 1}],
                "missing": [],
                "leftover": [],
            },
            {
                "pairs": [{"id": "B", "measurement": 0, "deviation": -3}],
                "missing": [],
                "leftover": [],
            },
        ],
    }


def test_signed_deviation_direction():
    resp = post(_body(measurements=[[97], [205]]))
    assert resp.status_code == 200
    deviations = [
        pair["deviation"] for bar in resp.json()["bars"] for pair in bar["pairs"]
    ]
    assert deviations == [-3, 5]


def test_tolerance_boundary():
    # |105 - 100| = 5 恰等于公差，可配对；|194 - 200| = 6 超出，不可配对。
    resp = post(_body(measurements=[[105], [194]]))
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert bars[0]["pairs"] == [{"id": "A", "measurement": 0, "deviation": 5}]
    assert bars[1] == {"pairs": [], "missing": ["B"], "leftover": [0]}
    assert resp.json()["qualified"] is False


def test_missing_and_leftover_reported_per_bar():
    resp = post(_body(measurements=[[], [200, 999]]))
    assert resp.status_code == 200
    assert resp.json()["bars"] == [
        {"pairs": [], "missing": ["A"], "leftover": []},
        {
            "pairs": [{"id": "B", "measurement": 0, "deviation": 0}],
            "missing": [],
            "leftover": [1],
        },
    ]
    assert resp.json()["qualified"] is False


def test_no_cross_bar_matching():
    # 实测 100 在 B 所在根上，A 不能跨根配对。
    resp = post(_body(measurements=[[], [100]]))
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert bars[0] == {"pairs": [], "missing": ["A"], "leftover": []}
    assert bars[1] == {"pairs": [], "missing": ["B"], "leftover": [0]}


def test_pair_count_then_deviation_then_lexicographic():
    body = _body(
        items=[{"id": "a", "length": 10}, {"id": "b", "length": 10}],
        bars=[{"item_ids": ["a", "b"]}],
        measurements=[[10, 10]],
        tolerance=0,
    )
    resp = post(body)
    assert resp.status_code == 200
    assert resp.json()["bars"][0]["pairs"] == [
        {"id": "a", "measurement": 0, "deviation": 0},
        {"id": "b", "measurement": 1, "deviation": 0},
    ]


def test_empty_measurements_allowed():
    resp = post(_body(measurements=[[], []]))
    assert resp.status_code == 200
    assert resp.json()["bars"] == [
        {"pairs": [], "missing": ["A"], "leftover": []},
        {"pairs": [], "missing": ["B"], "leftover": []},
    ]
    assert resp.json()["qualified"] is False


def test_plans_bars_accepted_end_to_end():
    items = [
        {"id": "A", "length": 3000},
        {"id": "B", "length": 2000},
        {"id": "C", "length": 2500},
        {"id": "D", "length": 1000},
    ]
    plan = client.post(
        "/plans", json={"stock_length": 6000, "kerf": 3, "items": items}
    ).json()
    resp = post(
        _body(
            items=items,
            bars=plan["bars"],
            measurements=[[3000], [2005, 2500, 999]],
            tolerance=5,
        )
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["qualified"] is True
    assert data["bars"][0]["pairs"] == [
        {"id": "A", "measurement": 0, "deviation": 0}
    ]
    assert data["bars"][1]["pairs"] == [
        {"id": "B", "measurement": 0, "deviation": 5},
        {"id": "C", "measurement": 1, "deviation": 0},
        {"id": "D", "measurement": 2, "deviation": -1},
    ]


def test_non_json_body_rejected():
    resp = client.post(
        "/inspections", content="not json", headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 422


def test_json_array_body_rejected():
    resp = client.post("/inspections", json=[1, 2, 3])
    assert resp.status_code == 422


def test_missing_top_field_rejected():
    for omitted in ("items", "bars", "measurements", "tolerance"):
        bad = {k: v for k, v in _body().items() if k != omitted}
        assert post(bad).status_code == 422


def test_unexpected_field_rejected():
    assert post(_body(extra=1)).status_code == 422


def test_items_validation_reused():
    # 件数越界、id 重复、非正长度、非字符串 id 均为 422。
    assert post(_body(items=[])).status_code == 422
    fifteen = [{"id": f"i{i}", "length": 1} for i in range(15)]
    assert post(_body(items=fifteen)).status_code == 422
    dup = [{"id": "A", "length": 1}, {"id": "A", "length": 2}]
    assert post(_body(items=dup)).status_code == 422
    assert post(_body(items=[{"id": "A", "length": 0}])).status_code == 422
    assert post(_body(items=[{"id": 7, "length": 1}])).status_code == 422


def test_tolerance_must_be_non_negative_integer():
    for bad in (-1, 1.0, "1", True):
        assert post(_body(tolerance=bad)).status_code == 422


def test_bars_structure_rejected():
    assert post(_body(bars=[])).status_code == 422
    assert post(_body(bars=[{"item_ids": []}])).status_code == 422
    assert post(_body(bars=[1, 2])).status_code == 422
    assert post(_body(bars=[{"item_ids": [1]}])).status_code == 422


def test_measurements_structure_rejected():
    assert post(_body(measurements="x")).status_code == 422
    # 与 bars 不等长。
    assert post(_body(measurements=[[100]])).status_code == 422
    # 单根不是数组。
    assert post(_body(measurements=[100, [200]])).status_code == 422
    # 非正整数 / 非整数实测值。
    assert post(_body(measurements=[[0], [200]])).status_code == 422
    assert post(_body(measurements=[[1.5], [200]])).status_code == 422
    assert post(_body(measurements=[[True], [200]])).status_code == 422


def test_total_measurements_bound():
    items = [{"id": f"i{i}", "length": 1} for i in range(14)]
    bars = [{"item_ids": [f"i{i}"]} for i in range(14)]
    measurements = [[1] for _ in range(13)] + [[1, 1]]
    assert (
        post(_body(items=items, bars=bars, measurements=measurements)).status_code
        == 422
    )
    # 恰好 14 条则合法。
    measurements = [[1] for _ in range(14)]
    resp = post(_body(items=items, bars=bars, measurements=measurements))
    assert resp.status_code == 200
    assert resp.json()["qualified"] is True


def test_item_id_must_appear_exactly_once_in_bars():
    # 未知 id。
    assert post(_body(bars=[{"item_ids": ["A"]}, {"item_ids": ["X"]}])).status_code == 422
    # 同一 id 出现在两根。
    assert post(_body(bars=[{"item_ids": ["A", "B"]}, {"item_ids": ["B"]}])).status_code == 422
    # 同一根内重复。
    assert post(_body(bars=[{"item_ids": ["A", "A"]}, {"item_ids": ["B"]}])).status_code == 422
    # item 未出现在 bars 中。
    items = [
        {"id": "A", "length": 100},
        {"id": "B", "length": 200},
        {"id": "C", "length": 300},
    ]
    assert post(_body(items=items, bars=[{"item_ids": ["A"]}, {"item_ids": ["B"]}])).status_code == 422

"""POST /inspections 接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(body):
    return client.post("/inspections", json=body)


def _items(*specs):
    return [{"id": gid, "length": length} for gid, length in specs]


def test_qualified_end_to_end_with_plans_bars():
    # /plans 的 bars 可直接作为 inspections 的 bars。
    plan = client.post(
        "/plans",
        json={
            "stock_length": 6000,
            "kerf": 3,
            "items": _items(
                ("A", 3000), ("B", 2000), ("C", 2500), ("D", 1000)
            ),
        },
    ).json()
    resp = post(
        {
            "tolerance": 2,
            "items": _items(
                ("A", 3000), ("B", 2000), ("C", 2500), ("D", 1000)
            ),
            "bars": plan["bars"],
            "measurements": [[3002], [2001, 2500, 1000]],
        }
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tolerance"] == 2
    assert data["bar_count"] == 2
    assert data["qualified"] is True
    assert data["inspections"] == [
        {
            "bar": 0,
            "pairs": [
                {"id": "A", "measurement_index": 0, "deviation": 2},
            ],
            "missing_ids": [],
            "surplus_measurements": [],
            "qualified": True,
        },
        {
            "bar": 1,
            "pairs": [
                {"id": "B", "measurement_index": 0, "deviation": 1},
                {"id": "C", "measurement_index": 1, "deviation": 0},
                {"id": "D", "measurement_index": 2, "deviation": 0},
            ],
            "missing_ids": [],
            "surplus_measurements": [],
            "qualified": True,
        },
    ]


def test_missing_and_surplus_mark_unqualified():
    resp = post(
        {
            "tolerance": 1,
            "items": _items(("a", 100), ("b", 200)),
            "bars": [{"item_ids": ["a", "b"]}],
            "measurements": [[99, 300]],
        }
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()["inspections"][0]
    assert entry["pairs"] == [
        {"id": "a", "measurement_index": 0, "deviation": -1}
    ]
    assert entry["missing_ids"] == ["b"]
    assert entry["surplus_measurements"] == [1]
    assert entry["qualified"] is False
    assert resp.json()["qualified"] is False


def test_signed_deviation_and_lexicographic_tiebreak():
    # a,b 标称均为 10，实测 10、9，容差 1：两种满配偏差和均为 1，
    # 取 (a,0),(b,1)。
    resp = post(
        {
            "tolerance": 1,
            "items": _items(("a", 10), ("b", 10)),
            "bars": [{"item_ids": ["a", "b"]}],
            "measurements": [[10, 9]],
        }
    )
    assert resp.status_code == 200, resp.text
    pairs = resp.json()["inspections"][0]["pairs"]
    assert pairs == [
        {"id": "a", "measurement_index": 0, "deviation": 0},
        {"id": "b", "measurement_index": 1, "deviation": -1},
    ]


def test_empty_measurements_allowed():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10), ("b", 20)),
            "bars": [{"item_ids": ["a"]}, {"item_ids": ["b"]}],
            "measurements": [[], [20]],
        }
    )
    assert resp.status_code == 200, resp.text
    inspections = resp.json()["inspections"]
    assert inspections[0]["missing_ids"] == ["a"]
    assert inspections[0]["pairs"] == []
    assert inspections[1]["qualified"] is True
    assert resp.json()["qualified"] is False


def test_measurements_not_shared_across_bars():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10), ("b", 5), ("c", 5)),
            "bars": [{"item_ids": ["a", "b"]}, {"item_ids": ["c"]}],
            "measurements": [[5], []],
        }
    )
    assert resp.status_code == 200, resp.text
    first, second = resp.json()["inspections"]
    assert [(p["id"], p["measurement_index"]) for p in first["pairs"]] == [
        ("b", 0)
    ]
    assert first["missing_ids"] == ["a"]
    assert second["missing_ids"] == ["c"]


def test_duplicate_id_within_items_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10), ("a", 20)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [[]],
        }
    )
    assert resp.status_code == 422
    assert "重复" in resp.json()["detail"]


def test_id_missing_from_bars_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10), ("b", 20)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [[]],
        }
    )
    assert resp.status_code == 422
    assert "未在 bars 中出现" in resp.json()["detail"]


def test_id_twice_in_bars_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10)),
            "bars": [{"item_ids": ["a"]}, {"item_ids": ["a"]}],
            "measurements": [[], []],
        }
    )
    assert resp.status_code == 422
    assert "重复" in resp.json()["detail"]


def test_unknown_id_in_bars_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10)),
            "bars": [{"item_ids": ["a"]}, {"item_ids": ["zzz"]}],
            "measurements": [[], []],
        }
    )
    assert resp.status_code == 422
    assert "未声明" in resp.json()["detail"]


def test_measurements_length_must_equal_bars():
    body = {
        "tolerance": 0,
        "items": _items(("a", 10), ("b", 20)),
        "bars": [{"item_ids": ["a"]}, {"item_ids": ["b"]}],
        "measurements": [[]],
    }
    assert post(body).status_code == 422
    body["measurements"] = [[], [], []]
    assert post(body).status_code == 422


def test_measurement_must_be_positive_integer():
    for bad in (0, -1, 1.5, "9", True):
        resp = post(
            {
                "tolerance": 0,
                "items": _items(("a", 10)),
                "bars": [{"item_ids": ["a"]}],
                "measurements": [[bad]],
            }
        )
        assert resp.status_code == 422, bad


def test_measurements_entry_must_be_array():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [9],
        }
    )
    assert resp.status_code == 422


def test_more_than_fourteen_measurements_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [[5] * 15],
        }
    )
    assert resp.status_code == 422
    assert "14" in resp.json()["detail"]


def test_fourteen_measurements_accepted():
    # 1 件 + 14 条实测：全单上限恰好为 14。
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 5)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [[5] * 14],
        }
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()["inspections"][0]
    assert entry["surplus_measurements"] == list(range(1, 14))


def test_tolerance_must_be_non_negative_integer():
    for bad in (-1, 1.0, "1", True):
        resp = post(
            {
                "tolerance": bad,
                "items": _items(("a", 10)),
                "bars": [{"item_ids": ["a"]}],
                "measurements": [[]],
            }
        )
        assert resp.status_code == 422


def test_item_count_bounds():
    assert post(
        {
            "tolerance": 0,
            "items": [],
            "bars": [],
            "measurements": [],
        }
    ).status_code == 422

    fifteen = _items(*[(f"i{i}", 1) for i in range(15)])
    bars = [{"item_ids": [f"i{i}"]} for i in range(15)]
    assert post(
        {
            "tolerance": 0,
            "items": fifteen,
            "bars": bars,
            "measurements": [[] for _ in range(15)],
        }
    ).status_code == 422


def test_missing_top_field_rejected():
    base = {
        "tolerance": 0,
        "items": _items(("a", 10)),
        "bars": [{"item_ids": ["a"]}],
        "measurements": [[]],
    }
    for omitted in ("items", "bars", "measurements", "tolerance"):
        bad = {k: v for k, v in base.items() if k != omitted}
        assert post(bad).status_code == 422


def test_unexpected_field_rejected():
    resp = post(
        {
            "tolerance": 0,
            "items": _items(("a", 10)),
            "bars": [{"item_ids": ["a"]}],
            "measurements": [[]],
            "extra": 1,
        }
    )
    assert resp.status_code == 422


def test_non_json_body_rejected():
    resp = client.post(
        "/inspections", content="not json", headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 422


def test_json_array_body_rejected():
    assert post([1, 2, 3]).status_code == 422


def test_bar_structure_still_validated():
    # bar 必须是对象、item_ids 必须是非空字符串数组。
    for bad_bars in ([1], [{"item_ids": []}], [{"item_ids": [1]}]):
        resp = post(
            {
                "tolerance": 0,
                "items": _items(("a", 10)),
                "bars": bad_bars,
                "measurements": [[] for _ in bad_bars],
            }
        )
        assert resp.status_code == 422

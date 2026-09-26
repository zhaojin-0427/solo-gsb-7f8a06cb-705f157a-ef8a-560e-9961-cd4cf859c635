"""POST /plans 接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(body):
    return client.post("/plans", json=body)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_valid_request():
    resp = post(
        {
            "stock_length": 6000,
            "kerf": 3,
            "items": [
                {"id": "A", "length": 3000},
                {"id": "B", "length": 2000},
                {"id": "C", "length": 2500},
                {"id": "D", "length": 1000},
            ],
        }
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["bar_count"] == 2
    assert data["bars"] == [
        {"item_ids": ["A"], "occupied_length": 3000, "remaining_length": 3000},
        {"item_ids": ["B", "C", "D"], "occupied_length": 5506, "remaining_length": 494},
    ]


def test_single_item_fills_bar():
    resp = post({"stock_length": 100, "kerf": 10, "items": [{"id": "x", "length": 100}]})
    assert resp.status_code == 200
    assert resp.json()["bars"] == [
        {"item_ids": ["x"], "occupied_length": 100, "remaining_length": 0}
    ]


def test_oversized_item_rejected():
    resp = post({"stock_length": 10, "kerf": 0, "items": [{"id": "x", "length": 11}]})
    assert resp.status_code == 422
    assert "超过原料长度" in resp.json()["detail"]


def test_duplicate_id_rejected():
    resp = post(
        {
            "stock_length": 100,
            "kerf": 0,
            "items": [{"id": "x", "length": 1}, {"id": "x", "length": 2}],
        }
    )
    assert resp.status_code == 422
    assert "重复" in resp.json()["detail"]


def test_float_integer_rejected():
    resp = post({"stock_length": 10.0, "kerf": 0, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422
    assert "整数" in resp.json()["detail"]


def test_numeric_string_rejected():
    resp = post({"stock_length": "10", "kerf": 0, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422


def test_boolean_rejected():
    resp = post({"stock_length": True, "kerf": 0, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422


def test_non_positive_stock_rejected():
    resp = post({"stock_length": 0, "kerf": 0, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422


def test_negative_kerf_rejected():
    resp = post({"stock_length": 10, "kerf": -1, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422


def test_zero_or_negative_item_length_rejected():
    for bad in (0, -3):
        resp = post(
            {"stock_length": 10, "kerf": 0, "items": [{"id": "x", "length": bad}]}
        )
        assert resp.status_code == 422


def test_item_count_bounds():
    resp = post({"stock_length": 10, "kerf": 0, "items": []})
    assert resp.status_code == 422

    fifteen = [{"id": f"i{i}", "length": 1} for i in range(15)]
    resp = post({"stock_length": 10, "kerf": 0, "items": fifteen})
    assert resp.status_code == 422


def test_non_string_id_rejected():
    resp = post({"stock_length": 10, "kerf": 0, "items": [{"id": 7, "length": 1}]})
    assert resp.status_code == 422


def test_missing_field_rejected():
    resp = post({"kerf": 0, "items": [{"id": "x", "length": 1}]})
    assert resp.status_code == 422

    resp = post({"stock_length": 10, "kerf": 0, "items": [{"id": "x"}]})
    assert resp.status_code == 422


def test_unexpected_field_rejected():
    resp = post(
        {
            "stock_length": 10,
            "kerf": 0,
            "items": [{"id": "x", "length": 1}],
            "extra": 1,
        }
    )
    assert resp.status_code == 422

    resp = post(
        {
            "stock_length": 10,
            "kerf": 0,
            "items": [{"id": "x", "length": 1, "width": 2}],
        }
    )
    assert resp.status_code == 422


def test_non_json_body_rejected():
    resp = client.post("/plans", content="not json", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 422


def test_json_array_body_rejected():
    resp = client.post("/plans", json=[1, 2, 3])
    assert resp.status_code == 422

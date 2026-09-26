"""POST /schedules 接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(body):
    return client.post("/schedules", json=body)


def _bars(n):
    return [{"item_ids": [f"i{j}"], "occupied_length": 1, "remaining_length": 0} for j in range(n)]


def _job(duration=1, release=0, due=0, blade="A"):
    return {"duration": duration, "release": release, "due": due, "blade": blade}


def test_valid_single_bar_uses_initial_blade():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 3,
            "bars": [{"item_ids": ["A"], "occupied_length": 5, "remaining_length": 5}],
            "jobs": [_job(duration=5, due=10, blade="B")],
        }
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "initial_blade": "A",
        "changeover": 3,
        "bar_count": 1,
        "schedule": [
            {
                "bar": 0,
                "item_ids": ["A"],
                "changeover": 3,
                "start": 3,
                "finish": 8,
                "tardiness": 0,
            }
        ],
        "max_tardiness": 0,
        "total_tardiness": 0,
        "makespan": 8,
    }


def test_valid_full_example():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 1,
            "bars": [
                {"item_ids": ["a"]},
                {"item_ids": ["b"]},
                {"item_ids": ["c"]},
                {"item_ids": ["d"]},
            ],
            "jobs": [
                {"duration": 2, "release": 1, "due": 7, "blade": "A"},
                {"duration": 2, "release": 4, "due": 7, "blade": "B"},
                {"duration": 5, "release": 2, "due": 11, "blade": "B"},
                {"duration": 3, "release": 4, "due": 0, "blade": "B"},
            ],
        }
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [entry["bar"] for entry in data["schedule"]] == [0, 3, 1, 2]
    assert data["max_tardiness"] == 7
    assert data["total_tardiness"] == 12
    assert data["makespan"] == 14


def test_plans_bars_accepted_end_to_end():
    # /plans 的输出元素（含 occupied_length/remaining_length）可直接作为 bars。
    plan = client.post(
        "/plans",
        json={
            "stock_length": 6000,
            "kerf": 3,
            "items": [
                {"id": "A", "length": 3000},
                {"id": "B", "length": 2000},
                {"id": "C", "length": 2500},
                {"id": "D", "length": 1000},
            ],
        },
    ).json()
    resp = post(
        {
            "initial_blade": "S1",
            "changeover": 2,
            "bars": plan["bars"],
            "jobs": [
                {"duration": 10, "release": 0, "due": 20, "blade": "S1"},
                {"duration": 30, "release": 0, "due": 100, "blade": "S2"},
            ],
        }
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["bar_count"] == 2
    assert [entry["item_ids"] for entry in data["schedule"]] == [["A"], ["B", "C", "D"]]
    assert [entry["changeover"] for entry in data["schedule"]] == [0, 2]


def test_lexicographic_tiebreak():
    # 对称工件、同刀具：指标全平，取索引序列 [0,1,2]。
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": _bars(3),
            "jobs": [_job(duration=1, due=100)] * 3,
        }
    )
    assert resp.status_code == 200, resp.text
    assert [e["bar"] for e in resp.json()["schedule"]] == [0, 1, 2]


def test_non_json_body_rejected():
    resp = client.post(
        "/schedules", content="not json", headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 422


def test_json_array_body_rejected():
    resp = client.post("/schedules", json=[1, 2, 3])
    assert resp.status_code == 422


def test_missing_top_field_rejected():
    body = {
        "initial_blade": "A",
        "changeover": 0,
        "bars": _bars(1),
        "jobs": [_job()],
    }
    for omitted in ("bars", "jobs", "initial_blade", "changeover"):
        bad = {k: v for k, v in body.items() if k != omitted}
        assert post(bad).status_code == 422


def test_unexpected_field_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": _bars(1),
            "jobs": [_job()],
            "extra": 1,
        }
    )
    assert resp.status_code == 422


def test_length_mismatch_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": _bars(2),
            "jobs": [_job()],
        }
    )
    assert resp.status_code == 422
    assert "等长" in resp.json()["detail"]


def test_bar_count_bounds():
    for n in (0, 10):
        resp = post(
            {
                "initial_blade": "A",
                "changeover": 0,
                "bars": _bars(n),
                "jobs": [_job() for _ in range(n)],
            }
        )
        assert resp.status_code == 422


def test_empty_item_ids_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": [{"item_ids": []}],
            "jobs": [_job()],
        }
    )
    assert resp.status_code == 422


def test_non_string_item_id_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": [{"item_ids": [1]}],
            "jobs": [_job()],
        }
    )
    assert resp.status_code == 422


def test_bar_not_object_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": [1],
            "jobs": [_job()],
        }
    )
    assert resp.status_code == 422


def test_job_not_object_rejected():
    resp = post(
        {
            "initial_blade": "A",
            "changeover": 0,
            "bars": _bars(1),
            "jobs": [1],
        }
    )
    assert resp.status_code == 422


def test_duration_must_be_positive_integer():
    for bad in (0, -1):
        resp = post(
            {
                "initial_blade": "A",
                "changeover": 0,
                "bars": _bars(1),
                "jobs": [_job(duration=bad)],
            }
        )
        assert resp.status_code == 422


def test_release_due_non_negative():
    for field in ("release", "due"):
        job = _job()
        job[field] = -1
        resp = post(
            {
                "initial_blade": "A",
                "changeover": 0,
                "bars": _bars(1),
                "jobs": [job],
            }
        )
        assert resp.status_code == 422


def test_blade_must_be_non_empty_string():
    for bad in ("", 7):
        resp = post(
            {
                "initial_blade": "A",
                "changeover": 0,
                "bars": _bars(1),
                "jobs": [_job(blade=bad)],
            }
        )
        assert resp.status_code == 422


def test_initial_blade_must_be_non_empty_string():
    for bad in ("", 7):
        resp = post(
            {
                "initial_blade": bad,
                "changeover": 0,
                "bars": _bars(1),
                "jobs": [_job()],
            }
        )
        assert resp.status_code == 422


def test_changeover_non_negative_integer():
    for bad in (-1, 1.0, "1", True):
        resp = post(
            {
                "initial_blade": "A",
                "changeover": bad,
                "bars": _bars(1),
                "jobs": [_job()],
            }
        )
        assert resp.status_code == 422


def test_float_and_boolean_ints_rejected():
    base = {
        "initial_blade": "A",
        "changeover": 0,
        "bars": _bars(1),
        "jobs": [{"duration": 1, "release": 0, "due": 0, "blade": "A"}],
    }
    bad = {"duration": 1.0, "release": 0, "due": 0, "blade": "A"}
    body = {**base, "jobs": [bad]}
    assert post(body).status_code == 422

    bad = {"duration": True, "release": 0, "due": 0, "blade": "A"}
    body = {**base, "jobs": [bad]}
    assert post(body).status_code == 422

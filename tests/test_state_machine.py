import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post("/api/clear")
        yield c
        c.post("/api/clear")


def _press(client, pin, kind="down"):
    client.post("/api/debug/press", json={"pin": pin, "kind": kind})


def test_toggle_course_selection(client):
    state = client.get("/api/state").json()
    course = state["courses"][0]
    course_id, pin = course["course_id"], course["button_gpio_pin"]

    _press(client, pin)
    state = client.get("/api/state").json()
    assert course_id in state["history_course_ids"]

    _press(client, pin)
    state = client.get("/api/state").json()
    assert course_id not in state["history_course_ids"]


def test_confirm_requires_at_least_one_skill(client):
    state = client.get("/api/state").json()
    clear_pin = state["clear_pin"]

    _press(client, clear_pin)
    state = client.get("/api/state").json()
    assert state["confirmed"] is False
    assert state["history_course_ids"] == []


def test_confirm_sequences_through_projects_then_exits(client):
    state = client.get("/api/state").json()
    clear_pin = state["clear_pin"]

    # Pick a course that appears in at least one project, so the sequence is non-empty.
    target_skill = state["projects"][0]["skill_ids"][0]
    course = next(c for c in state["courses"] if c["course_id"] == target_skill)
    _press(client, course["button_gpio_pin"])

    _press(client, clear_pin)
    state = client.get("/api/state").json()
    assert state["confirmed"] is True
    assert state["project_index"] == 0
    total = len(state["project_sequence"])
    assert total >= 1

    # Advance through every remaining project without exiting early.
    for expected_index in range(1, total):
        _press(client, clear_pin)
        state = client.get("/api/state").json()
        assert state["confirmed"] is True, f"exited early at index {expected_index}"
        assert state["project_index"] == expected_index

    # Only the press *after* the last project should exit.
    _press(client, clear_pin)
    state = client.get("/api/state").json()
    assert state["confirmed"] is False
    assert state["history_course_ids"] == []
    assert state["project_sequence"] == []


def test_course_toggle_is_ignored_once_confirmed(client):
    state = client.get("/api/state").json()
    clear_pin = state["clear_pin"]
    course = state["courses"][0]

    _press(client, course["button_gpio_pin"])
    _press(client, clear_pin)  # confirm
    state = client.get("/api/state").json()
    assert state["confirmed"] is True
    selected_before = set(state["history_course_ids"])

    # Pressing a different course button while confirmed should have no effect.
    other_course = next(c for c in state["courses"] if c["course_id"] != course["course_id"])
    _press(client, other_course["button_gpio_pin"])
    state = client.get("/api/state").json()
    assert set(state["history_course_ids"]) == selected_before


def test_manual_clear_resets_everything(client):
    state = client.get("/api/state").json()
    pin = state["courses"][0]["button_gpio_pin"]

    _press(client, pin)
    client.post("/api/clear")
    state = client.get("/api/state").json()
    assert state["history_course_ids"] == []
    assert state["confirmed"] is False
    assert state["project_sequence"] == []
    assert state["project_index"] == 0

from __future__ import annotations

from common.models import Chat, City, Interest, Like, Message, Subscription, User
from config import SessionLocal
from scripts.seed_demo import seed_demo


PHONE = "70000000999"
CODE = "000000"


def _assert_ok(response):
    assert response.status_code in {200, 201}, response.text
    return response.json() if response.content else None


def _authorization(token_payload):
    token = token_payload["access_token"]
    return {
        "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}"
    }


def test_seed_is_idempotent(isolated_database):
    first = seed_demo()
    second = seed_demo()
    assert first == second

    with SessionLocal() as session:
        assert session.query(City).count() == 2
        assert session.query(Interest).count() == 12
        assert session.query(Subscription).count() == 3
        assert (
            session.query(User).filter(User.phone_number.like("700000000%")).count()
            == 14
        )
        assert session.query(Like).count() == 5
        assert session.query(Chat).count() == 1
        assert session.query(Message).count() == 3


def test_http_demo_smoke_flow(client):
    health = _assert_ok(client.get("/health"))
    assert health["status"] == "ok"

    sms = _assert_ok(client.post("/auth/send_code", params={"phone_number": PHONE}))
    assert sms["verification_code"] == CODE

    registered = _assert_ok(
        client.post(
            "/auth/register",
            json={
                "phone_number": PHONE,
                "first_name": "Тест",
                "last_name": "Смоук",
                "date_of_birth": "1996-05-20",
                "gender": "female",
                "city_name": "Демо-Сити (Демо-регион Север)",
                "about_me": "Профиль smoke-теста",
            },
        )
    )
    headers = _authorization(registered)

    refreshed = _assert_ok(
        client.post(
            "/auth/refresh_token",
            params={"refresh_token": registered["refresh_token"]},
        )
    )
    assert refreshed["refresh_token"]

    whoami = _assert_ok(client.get("/auth/whoami", headers=headers))
    assert whoami["id"]

    profile = _assert_ok(client.get("/user/me", headers=headers))
    assert profile["first_name"] == "Тест"

    _assert_ok(
        client.put(
            "/user/update_user",
            headers=headers,
            json={"about_me": "Обновлённый smoke-профиль"},
        )
    )
    updated = _assert_ok(client.get("/user/me", headers=headers))
    assert updated["about_me"] == "Обновлённый smoke-профиль"

    matches = _assert_ok(client.get("/match/find_matches", headers=headers))
    assert isinstance(matches, list)

    _assert_ok(client.post("/likes/like/1", headers=headers))
    _assert_ok(client.post("/likes/dislike/2", headers=headers))
    liked_users = _assert_ok(client.get("/likes/liked_users", headers=headers))
    assert any(user["id"] == 1 for user in liked_users)

    chat = _assert_ok(
        client.post("/communication/create_chat", headers=headers, json={"user_id": 1})
    )
    assert chat["chat_id"]
    chats = _assert_ok(client.get("/communication/get_chats", headers=headers))
    assert any(item["chat_id"] == chat["chat_id"] for item in chats)

    subscriptions = _assert_ok(client.get("/subscriptions/", headers=headers))
    assert len(subscriptions["subscriptions"]) == 3

    _assert_ok(client.post("/auth/send_code", params={"phone_number": PHONE}))
    logged_in = _assert_ok(
        client.post("/auth/login", params={"phone_number": PHONE, "code": CODE})
    )
    assert logged_in["refresh_token"]

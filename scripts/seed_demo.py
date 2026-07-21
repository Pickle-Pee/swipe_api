"""Create deterministic, fictional data for the local demo environment."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from common.models import (
    Chat,
    City,
    Interest,
    Like,
    Message,
    Region,
    Subscription,
    User,
    UserGeolocation,
    UserInterest,
    UserPhoto,
)
from common.models.likes_models import UserLike
from common.models.user_models import UserAttributes
from common.models.enums import (
    AlcoholAttitudeEnum,
    AppearanceEnum,
    ChildrenEnum,
    ReligionEnum,
    SmokingAttitudeEnum,
    WhatLookingForEnum,
)
from config import BUCKET_PROFILE_IMAGES, DEMO_STORAGE_DIR, IS_DEMO, SessionLocal


REGIONS = {
    "Демо-регион Север": ("Демо-Сити", 55.751244, 37.618423),
    "Демо-регион Юг": ("Тестоград", 59.938630, 30.314130),
}

INTERESTS = (
    "Путешествия",
    "Кино",
    "Музыка",
    "Книги",
    "Фотография",
    "Прогулки",
    "Кулинария",
    "Настольные игры",
    "Спорт",
    "Театр",
    "Технологии",
    "Волонтёрство",
)

SUBSCRIPTIONS = (
    ("Demo Start", 0.0, 7, "Базовые возможности demo"),
    ("Demo Plus", 299.0, 30, "Безлимитные лайки и просмотр симпатий"),
    ("Demo Premium", 599.0, 30, "Все demo-возможности"),
)

PEOPLE = (
    ("70000000001", "Алекс", "Северин", "male", date(1996, 4, 12)),
    ("70000000002", "Мира", "Лесная", "female", date(1997, 8, 3)),
    ("70000000003", "Никита", "Речной", "male", date(1993, 1, 21)),
    ("70000000004", "София", "Ясная", "female", date(1998, 11, 15)),
    ("70000000005", "Даниил", "Ветров", "male", date(1995, 6, 7)),
    ("70000000006", "Полина", "Добрая", "female", date(1999, 2, 26)),
    ("70000000007", "Марк", "Озерный", "male", date(1992, 9, 9)),
    ("70000000008", "Ева", "Светлая", "female", date(1996, 12, 18)),
    ("70000000009", "Лев", "Мирный", "male", date(1994, 5, 30)),
    ("70000000010", "Анна", "Радова", "female", date(1997, 7, 14)),
    ("70000000011", "Роман", "Звездный", "male", date(1991, 10, 5)),
    ("70000000012", "Лада", "Весенняя", "female", date(1995, 3, 22)),
    ("70000000013", "Саша", "Горизонт", "non-binary", date(1998, 1, 11)),
    ("70000000014", "Женя", "Искра", "non-binary", date(1994, 7, 19)),
)


def _get_or_create(session, model, defaults=None, **lookup):
    instance = session.query(model).filter_by(**lookup).first()
    if instance is None:
        instance = model(**lookup, **(defaults or {}))
        session.add(instance)
        session.flush()
    return instance


def _write_avatar(index: int, name: str) -> str:
    file_name = f"demo-avatar-{index:02d}.svg"
    target = (
        Path(DEMO_STORAGE_DIR) / (BUCKET_PROFILE_IMAGES or "profile-images") / file_name
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    color = (index * 37) % 360
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">'
        f'<rect width="512" height="512" fill="hsl({color},55%,65%)"/>'
        '<circle cx="256" cy="190" r="92" fill="#fff" fill-opacity=".8"/>'
        '<path d="M96 480c18-112 82-168 160-168s142 56 160 168" '
        'fill="#fff" fill-opacity=".8"/>'
        f'<text x="256" y="500" text-anchor="middle" font-size="22">{name}</text>'
        "</svg>"
    )
    if not target.exists() or target.read_text(encoding="utf-8") != svg:
        target.write_text(svg, encoding="utf-8")
    return f"/service/get_file/{file_name}"


def seed_demo() -> dict[str, int]:
    if not IS_DEMO:
        raise RuntimeError("Demo seed is allowed only when APP_ENV=demo")

    with SessionLocal() as session:
        cities = []
        coordinates = {}
        for region_name, (city_name, latitude, longitude) in REGIONS.items():
            region = _get_or_create(session, Region, name=region_name)
            city = _get_or_create(
                session, City, city_name=city_name, region_id=region.id
            )
            cities.append(city)
            coordinates[city.id] = (latitude, longitude)

        interests = [
            _get_or_create(session, Interest, interest_text=text) for text in INTERESTS
        ]
        for name, price, duration, features in SUBSCRIPTIONS:
            subscription = _get_or_create(session, Subscription, name=name)
            subscription.price = price
            subscription.duration = duration
            subscription.features = features
            subscription.price_minor = round(price * 100)
            subscription.currency = "RUB"
            subscription.duration_days = duration
            subscription.description = features
            subscription.is_active = True
            subscription.renewable = True

        users = []
        for index, (phone, first_name, last_name, gender, birthday) in enumerate(
            PEOPLE, 1
        ):
            city = cities[(index - 1) % len(cities)]
            user = _get_or_create(session, User, phone_number=phone)
            user.first_name = first_name
            user.last_name = last_name
            user.date_of_birth = birthday
            user.gender = gender
            user.verify = "approved"
            user.city_id = city.id
            user.about_me = (
                f"Вымышленный demo-профиль: {first_name}. Люблю новые знакомства "
                "и спокойные прогулки по городу."
            )
            user.status = "offline"
            user.deleted = False
            users.append(user)
            session.flush()

            attributes = _get_or_create(session, UserAttributes, user_id=user.id)
            attributes.height = 160 + index * 2
            attributes.smoking_attitude = SmokingAttitudeEnum.NON_SMOKER
            attributes.alcohol_attitude = AlcoholAttitudeEnum.MODERATE
            attributes.children_preference = ChildrenEnum.OPEN_TO_PARTNER_CHILDREN
            attributes.what_looking_for = WhatLookingForEnum.SERIOUS_RELATIONSHIP
            attributes.appearance = AppearanceEnum.NATURAL_SIMPLE
            attributes.religion = ReligionEnum.PREFERS_NOT_TO_SAY

            latitude, longitude = coordinates[city.id]
            geolocation = _get_or_create(
                session,
                UserGeolocation,
                defaults={"latitude": latitude, "longitude": longitude},
                user_id=user.id,
            )
            geolocation.latitude = latitude + index / 1000
            geolocation.longitude = longitude + index / 1000
            geolocation.updated_at = datetime.now()

            avatar_url = _write_avatar(index, first_name)
            photo = (
                session.query(UserPhoto)
                .filter_by(user_id=user.id, is_avatar=True)
                .first()
            )
            if photo is None:
                photo = UserPhoto(user_id=user.id, is_avatar=True, photo_url=avatar_url)
                session.add(photo)
            photo.photo_url = avatar_url
            photo.scale = 1.0
            photo.position_x = 0.0
            photo.position_y = 0.0

            for interest in (
                interests[(index - 1) % len(interests)],
                interests[index % len(interests)],
            ):
                _get_or_create(
                    session,
                    UserInterest,
                    user_id=user.id,
                    interest_id=interest.id,
                )
            _get_or_create(
                session, UserLike, defaults={"total_likes": 0}, user_id=user.id
            )

        for source_index, target_index, mutual in (
            (0, 1, True),
            (1, 0, True),
            (2, 3, False),
            (4, 5, False),
            (6, 7, False),
        ):
            like = _get_or_create(
                session,
                Like,
                user_id=users[source_index].id,
                liked_user_id=users[target_index].id,
            )
            like.mutual = mutual

        chat = (
            session.query(Chat)
            .filter_by(user1_id=users[0].id, user2_id=users[1].id)
            .first()
        )
        if chat is None:
            chat = Chat(user1_id=users[0].id, user2_id=users[1].id)
            session.add(chat)
            session.flush()

        messages = (
            (users[0].id, "Привет! Это готовый demo-чат."),
            (users[1].id, "Привет! Отлично, сообщения работают."),
            (users[0].id, "Можно продолжить разговор во Flutter-клиенте."),
        )
        for offset, (sender_id, content) in enumerate(messages):
            existing = (
                session.query(Message)
                .filter_by(chat_id=chat.id, content=content)
                .first()
            )
            if existing is None:
                session.add(
                    Message(
                        chat_id=chat.id,
                        sender_id=sender_id,
                        content=content,
                        status="read",
                        created_at=datetime.now() + timedelta(seconds=offset),
                    )
                )

        session.commit()
        return {
            "cities": len(cities),
            "interests": len(interests),
            "subscriptions": len(SUBSCRIPTIONS),
            "users": len(users),
            "likes": 5,
            "matches": 1,
            "chats": 1,
            "messages": len(messages),
        }


def main() -> None:
    summary = seed_demo()
    print(
        "Demo seed complete: "
        + ", ".join(f"{key}={value}" for key, value in summary.items())
    )


if __name__ == "__main__":
    main()

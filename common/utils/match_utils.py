import re
from common.models.interests_models import UserInterest
from common.models.favorite_models import Favorite
from config import SessionLocal


def parse_interests(interests_str):
    return re.findall(r'\w+', interests_str)


def check_if_favorite(user_id: int, other_user_id: int) -> bool:
    with SessionLocal() as db:
        favorite_entry = db.query(Favorite).filter(
            Favorite.user_id == user_id,
            Favorite.favorite_user_id == other_user_id
        ).first()

        return bool(favorite_entry)
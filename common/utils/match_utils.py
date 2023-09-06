import re
from common.models.interests_models import UserInterest
from common.models.favorite_models import Favorite
from config import SessionLocal


def parse_interests(interests_str):
    return re.findall(r'\w+', interests_str)


def calculate_match_percentage(user_id: int, other_user_id: int) -> float:
    with SessionLocal() as db:
        user_interests_obj = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
        other_interests_obj = db.query(UserInterest).filter(UserInterest.user_id == other_user_id).all()

        user_interests = set([ui.interest_id for ui in user_interests_obj])
        other_interests = set([oi.interest_id for oi in other_interests_obj])

        common_interests = user_interests.intersection(other_interests)
        total_interests = user_interests.union(other_interests)

        if total_interests:
            match_percentage = (len(common_interests) / len(total_interests)) * 100
            return round(match_percentage, 2)
        else:
            return 0.0


def check_if_favorite(user_id: int, other_user_id: int) -> bool:
    with SessionLocal() as db:
        favorite_entry = db.query(Favorite).filter(
            Favorite.user_id == user_id,
            Favorite.favorite_user_id == other_user_id
        ).first()

        return bool(favorite_entry)
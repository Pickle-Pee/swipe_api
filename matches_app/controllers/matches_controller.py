from fastapi import HTTPException, APIRouter, Depends
from typing import List
from common.schemas.match_schemas import MatchResponse
from common.models.user_models import User
from common.models.interests_models import UserInterest
from common.models.likes_models import Like, Dislike
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, SECRET_KEY
from datetime import datetime

# dir_path = os.path.dirname(os.path.realpath(__file__))
# model_path = os.path.join(dir_path, '..', 'utils', 'model.keras')
# model = load_model(model_path)

router = APIRouter(prefix="/match", tags=["Matches Controller"])


# @router.get("/find_matches_machine", response_model=List[MatchResponse])
# def find_matches(access_token: str = Depends(get_token)):
#     with SessionLocal() as db:
#         user_id = get_user_id_from_token(access_token, SECRET_KEY)
#         user = db.query(User).filter(User.id == user_id).first()
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
#
#         # Your existing code for fetching liked and disliked users
#         # ...
#
#         matches = []
#
#         all_users = db.query(User).filter(User.id != user_id).all()  # Your existing query
#
#         for other_user in all_users:
#             # Your existing code for calculating match percentage based on interests
#             # ...
#
#             # Prepare the data for the model
#             user_features = np.array([[user.age, 1 if user.gender == 'male' else 0, 1 if user.gender == 'female' else 0,
#                                        user.verify, 1]])  # Replace 1 with actual interest_id
#             other_user_features = np.array([[other_user.age, 1 if other_user.gender == 'male' else 0, 1 if other_user.
#                                            gender == 'female' else 0, other_user.verify, 1]])  # Replace 1 with actual interest_id
#
#             # Make a prediction using the model
#             prediction = model.predict([user_features, np.array([1])])  # Replace np.array([1]) with actual item_id
#
#             # Calculate match percentage based on the model's prediction
#             match_percentage = prediction[0][0] * 100
#
#             matches.append(
#                 MatchResponse(
#                     user_id=other_user.id,
#                     first_name=other_user.first_name,
#                     last_name=other_user.last_name,
#                     date_of_birth=other_user.date_of_birth,
#                     gender=other_user.gender if other_user.gender is not None else "Unknown",
#                     verify=other_user.verify,
#                     match_percentage=match_percentage
#                 )
#             )
#
#         # Sort the matches by match percentage
#         matches = sorted(matches, key=lambda x: x.match_percentage, reverse=True)
#
#         return matches[:10]


@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Получение списка ID пользователей, которых текущий пользователь уже лайкнул или дизлайкнул
        liked_users = db.query(Like.liked_user_id).filter(Like.user_id == user_id).all()
        disliked_users = db.query(Dislike.disliked_user_id).filter(
            Dislike.user_id == user_id,
            Dislike.timestamp > datetime.utcnow()
        ).all()

        liked_user_ids = [like.liked_user_id for like in liked_users]
        disliked_user_ids = [dislike.disliked_user_id for dislike in disliked_users]

        excluded_user_ids = liked_user_ids + disliked_user_ids

        user_interests_obj = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
        if not user_interests_obj:
            raise HTTPException(status_code=404, detail="User interests not found")

        user_interests = set([ui.interest_id for ui in user_interests_obj])

        matches = []

        # Исключаем пользователей, которых уже лайкнули или дизлайкнули
        all_users = db.query(User).filter(
            User.id != user_id,
            User.id.notin_(excluded_user_ids)
        ).all()

        for other_user in all_users:
            other_interests_obj = db.query(UserInterest).filter(UserInterest.user_id == other_user.id).all()

            other_interests = set([oi.interest_id for oi in other_interests_obj]) if other_interests_obj else set()

            common_interests = user_interests.intersection(other_interests)
            total_interests = user_interests.union(other_interests)

            if total_interests:
                match_percentage = (len(common_interests) / len(total_interests)) * 100
                match_percentage = round(match_percentage, 2)
            else:
                match_percentage = 0.0

            matches.append(
                MatchResponse(
                    user_id=other_user.id,
                    first_name=other_user.first_name,
                    last_name=other_user.last_name,
                    date_of_birth=other_user.date_of_birth,
                    gender=other_user.gender if other_user.gender is not None else "Unknown",
                    verify=other_user.verify,
                    match_percentage=match_percentage
                )
            )

        # Сортируем по проценту совпадений
        matches = sorted(matches, key=lambda x: x.match_percentage, reverse=True)

        return matches[:10]

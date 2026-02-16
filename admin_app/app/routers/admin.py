from fastapi import APIRouter, Depends

from common.models import Admin
from .. import schemas
from ..dependencies import get_current_admin

router = APIRouter(
    tags=["admin"],
)


@router.get("/whoami", response_model=schemas.AdminResponse, summary="Получение информации о текущем администраторе")
def who_am_i(current_admin: Admin = Depends(get_current_admin)):
    return current_admin

from fastapi import APIRouter 
from app.models.schemas import (
    HumanizeRequest,
    HumanizeResponse
)
from app.services.humanizer import Humanizer

router = APIRouter()

service = Humanizer()

@router.post(
    "/humanize",
    response_model=HumanizeResponse
)
async def humanize(
    request: HumanizeRequest
):
    return await service.rewrite(
        request.text
    )

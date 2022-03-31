import dataclasses
from typing import Optional

from fastapi import APIRouter
from starlette.requests import Request
from aiorq.app_server.schemas import JobResultModel, JobDefsModel

router = APIRouter()


@router.get("")
async def redis_info(request: Request):
    redis_info = await request.app.state.redis.redis_info()
    redis_info = [{"label":k,"value":v} for k,v in redis_info.items()]
    return {"items": redis_info}


import json

from fastapi import APIRouter, Depends
from starlette.requests import Request

router = APIRouter()


@router.get("/get_all_functions")
async def get_all_functions(request: Request):
    results = await request.app.state.redis.all_tasks()
    return {"results": json.loads(results)}
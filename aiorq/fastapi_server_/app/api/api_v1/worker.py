import json
import os
from fastapi import APIRouter, Depends
from starlette.requests import Request


router = APIRouter()


@router.get("/get_all_workers")
async def get_all_workers(request: Request):
    results = await request.app.state.redis.all_workers()
    results = [json.loads(v) for v in results]
    return {"results": results}




# @router.get("/log")
# async def logs(name: str):
#     log_file = os.path.join(constants.BASE_DIR, "logs", f"worker-{name}.log")
#     async with aiofiles.open(log_file, mode="r") as f:
#         content = await f.read()
#     return content

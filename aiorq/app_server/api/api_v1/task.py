from fastapi import APIRouter
from starlette.requests import Request

router = APIRouter()


@router.get("/get_job_funcs")
async def get_job_funcs(request: Request):
    results = await request.app.state.redis.get_job_funcs()
    return results

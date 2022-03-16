from typing import Optional

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import JobResultModel

router = APIRouter()


@router.get("/get_all_result", response_model=JobResultModel)
async def all_job_results(
        request: Request,
        function: Optional[str] = None,
        job_id: Optional[str] = None,
        start_time: Optional[str] = None,
        finish_time: Optional[str] = None,
        worker_name: Optional[str] = None,
        success: bool = None,
):
    query_ = {
        "worker_name":worker_name,
        "function":function
    }
    results_ = await request.app.state.redis.all_job_results()
    for k,v in query_.items():
        results_ = [result_ for result_ in results_ if result_.__dict__.get(k) == v]
    return {"rows": results_}


@router.delete("")
async def delete_result():
    ...

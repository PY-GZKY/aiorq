from typing import Optional

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import JobResultModel

router = APIRouter()


@router.get("/get_all_result", response_model=JobResultModel)
async def all_job_results(
        request: Request,
        task: Optional[str] = None,
        job_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        worker: Optional[str] = None,
        success: Optional[str] = None,
):
    all_result_ = await request.app.state.redis.all_job_results()
    print(all_result_)
    if worker:
        all_result_ = [result_ for result_ in all_result_ if result_.get("worker_name") == worker]
    if task:
        all_result_ = [result_ for result_ in all_result_ if result_.get("function") == task]
    if job_id:
        all_result_ = [result_ for result_ in all_result_ if result_.get("job_id") == job_id]

    return {"rows": all_result_}


@router.delete("")
async def delete_result():
    ...

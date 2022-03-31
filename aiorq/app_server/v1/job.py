import dataclasses
from typing import Optional

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import JobResultModel, JobDefsModel

router = APIRouter()


@router.get("/queued_jobs", response_model=JobDefsModel)
async def queued_jobs(
        request: Request,
        queue_name: str = "pai:queue",
        worker_name: str = None,
        function: str = None,
        job_id: str = None,
        state: str = None
):
    results_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    if worker_name:
        results_ = filter(lambda result: worker_name in dataclasses.asdict(result).get("worker_name"), results_)
    if function:
        results_ = filter(lambda result: function in dataclasses.asdict(result).get("function"), results_)
    if job_id:
        results_ = filter(lambda result: job_id in dataclasses.asdict(result).get("job_id"), results_)
    if state:
        results_ = filter(lambda result: state == dataclasses.asdict(result).get("state"), results_)
    return {"rows": list(results_)}


@router.get("/results", response_model=JobResultModel)
async def results(
        request: Request,
        worker_name: Optional[str] = None,
        function: Optional[str] = None,
        job_id: Optional[str] = None,
        start_time: Optional[str] = None,
        finish_time: Optional[str] = None,
        success: bool = None,
):
    results_ = await request.app.state.redis.all_job_results()
    if worker_name:
        results_ = filter(lambda result: worker_name in dataclasses.asdict(result).get("worker_name"), results_)
    if function:
        results_ = filter(lambda result: function in dataclasses.asdict(result).get("function"), results_)
    if job_id:
        results_ = filter(lambda result: job_id in dataclasses.asdict(result).get("job_id"), results_)
    if success is not None:
        results_ = filter(lambda result: success == dataclasses.asdict(result).get("success"), results_)
    return {"rows": list(results_)}


@router.delete("")
async def delete_result():
    ...

import dataclasses
from typing import Optional

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.jobs import Job
from aiorq.app_server.schemas import JobResultModel, JobDefsModel

router = APIRouter()


@router.get("/queued_jobs", response_model=JobDefsModel)
async def queued_jobs(request: Request, queue_name="pai:queue"):
    queued_jobs_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    return {"rows": queued_jobs_}

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
    query_ = {
        "worker_name": worker_name,
        "function": function,
        "job_id": job_id,
        "start_time": start_time,
        "finish_time": finish_time,
        "success": success
    }
    results_ = await request.app.state.redis.all_job_results()
    for k, v in query_.items():
        if v:
            results_ = filter(lambda result: dataclasses.asdict(result).get(k) == v, results_)
            results_ = list(results_)
    return {"rows": results_}


@router.delete("")
async def delete_result():
    ...

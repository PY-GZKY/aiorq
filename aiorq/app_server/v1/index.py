import asyncio
import dataclasses
import typing

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import IndecModel, JobDefModel, HealthCheckModel, JobDefsModel,WorkerListModel

router = APIRouter()


@router.get("/index", response_model=IndecModel)
async def index(request: Request):
    functions = await request.app.state.redis.get_job_funcs()
    workers = await request.app.state.redis.get_job_workers()
    # print(functions)
    # print(workers)
    return {"functions": functions, "workers": workers}


@router.get("/get_health_check", response_model=HealthCheckModel)
async def get_health_check(request: Request, worker_name):
    result = await request.app.state.redis._get_health_check(worker_name=worker_name)
    return result


@router.get("/enqueue_job_", response_model=JobDefModel)
async def enqueue_job_(request: Request):
    job = await request.app.state.redis.enqueue_job('say_hi', name="wutong", queue_name="pai:queue", job_try=2, defer_by=20)
    job_ = await job.info()
    # await job.abort()
    return job_


@router.get("/queued_jobs", response_model=JobDefsModel)
async def queued_jobs(request: Request, queue_name="pai:queue"):
    queued_jobs_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    return {"rows": queued_jobs_}


@router.get("/get_job_workers", response_model=WorkerListModel)
async def get_job_workers(
        request: Request,
        worker: typing.Optional[str] = None,
        queue: typing.Optional[str] = None,
        is_action: bool = None
):
    query_ = {
        "worker_name": worker,
        "queue_name": queue,
        "is_action": is_action
    }
    print(query_)
    results_ = await request.app.state.redis.get_job_workers()
    print(results_)
    for k, v in query_.items():
        if v is not None:
            results_ = filter(lambda result: dataclasses.asdict(result).get(k) == v, results_)
            results_ = list(results_)
    return {"workers":results_}


@router.get("/get_job_funcs")
async def get_job_funcs(request: Request):
    results = await request.app.state.redis.get_job_funcs()
    return results

# @router.get("/log")
# async def logs(name: str):
#     log_file = os.path.join(constants.BASE_DIR, "logs", f"worker-{name}.log")
#     async with aiofiles.open(log_file, mode="r") as f:
#         content = await f.read()
#     return content

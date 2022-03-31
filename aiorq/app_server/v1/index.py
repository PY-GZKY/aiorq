import dataclasses

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import IndecModel, JobDefModel, HealthCheckModel, WorkerListModel

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


@router.get("/enqueue_job", response_model=JobDefModel)
async def enqueue_job_(request: Request):
    job = await request.app.state.redis.enqueue_job('say_hello', name="wutong", queue_name="pai:queue2", job_try=1, defer_by=2)
    job_ = await job.info()
    # await job.abort()
    return job_


@router.get("/workers", response_model=WorkerListModel)
async def workers(
        request: Request,
        worker: str = None,
        queue: str = None,
        is_action: bool = None
):
    query_ = {
        "worker_name": worker,
        "queue_name": queue,
        "is_action": is_action
    }
    results_ = await request.app.state.redis.get_job_workers()
    if query_.get("worker_name"):
        results_ = filter(lambda result: query_.get("worker_name") in dataclasses.asdict(result).get("worker_name"), results_)
    if query_.get("queue_name"):
        results_ = filter(lambda result: query_.get("queue_name") in dataclasses.asdict(result).get("queue_name"), results_)
    if query_.get("is_action") is not None:
        results_ = filter(lambda result: query_.get("is_action") == dataclasses.asdict(result).get("is_action"), results_)
    results_ = list(results_)
    return {"workers": results_}


@router.get("/funcs")
async def get_job_funcs(request: Request):
    results = await request.app.state.redis.get_job_funcs()
    return results

# @router.get("/log")
# async def logs(name: str):
#     log_file = os.path.join(constants.BASE_DIR, "logs", f"worker-{name}.log")
#     async with aiofiles.open(log_file, mode="r") as f:
#         content = await f.read()
#     return content

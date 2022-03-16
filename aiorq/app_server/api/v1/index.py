from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import IndecModel, JobDefModel, HealthCheckModel, JobDefsModel

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
    job = await request.app.state.redis.enqueue_job('say_hi', name="wutong", _queue_name="pai:queue", _job_try=2,
                                                    _defer_by=100)
    job_ = await job.info()
    return job_


@router.get("/queued_jobs", response_model=JobDefsModel)
async def queued_jobs(request: Request, queue_name="pai:queue"):
    queued_jobs_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    return {"rows": queued_jobs_}


@router.get("/get_all_workers")
async def get_all_workers(request: Request):
    results = await request.app.state.redis.get_job_workers()
    return results


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

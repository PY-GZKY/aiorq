import json

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.app_server.schemas import IndecModel,JobDefModel
from aiorq.jobs import Job

router = APIRouter()


@router.get("/index", response_model=IndecModel)
async def index(request: Request):
    functions = await request.app.state.redis.get_job_funcs()
    workers = await request.app.state.redis.get_job_workers()
    return {"functions": functions, "workers": workers}



@router.get("/get_health_check")
async def get_health_check(request: Request, worker_name):
    result = await request.app.state.redis._get_health_check(worker_name=worker_name)
    return {"result": json.loads(result)}


@router.get("/enqueue_job_", response_model=JobDefModel)
async def enqueue_job_(request: Request):
    job = await request.app.state.redis.enqueue_job('say_hi',  name="wutong", _queue_name="pai:queue", _job_try=2)
    job_ = await job.info()
    return job_


@router.get("/queued_jobs")
async def queued_jobs(request: Request, queue_name="aiorq:queue"):
    queued_jobs_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    queued_jobs__ = []
    for queued_job_ in queued_jobs_:
        state = await Job(job_id=queued_job_.__dict__.get("job_id"), redis=request.app.state.redis,
                          _queue_name=queue_name).status()
        queued_job_.__dict__.update({"state": state})
        queued_jobs__.append(queued_job_)
    return {"queued_jobs": queued_jobs__}

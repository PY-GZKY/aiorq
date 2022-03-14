import json

from fastapi import APIRouter
from starlette.requests import Request

from aiorq.jobs import Job

router = APIRouter()


@router.get("/index")
async def index(request: Request):
    functions = await request.app.state.redis.all_tasks()
    workers = await request.app.state.redis.all_workers()
    results = await request.app.state.redis.all_job_results()
    functions_num = len(json.loads(functions))
    workers_num = len(workers)
    results_num = len(results)
    results = {"functions_num": functions_num, "workers_num": workers_num, "results_num": results_num}
    return {"results": results}


@router.get("/get_health_check")
async def get_health_check(request: Request, worker_name):
    result = await request.app.state.redis._get_health_check(worker_name=worker_name)
    return {"result": json.loads(result)}


@router.get("/enqueue_job_")
async def enqueue_job_(request: Request):
    job = await request.app.state.redis.enqueue_job('qy_spider_', _queue_name="comment_queue", _job_try=4)
    job_ = await job.info()
    return {"job_": job_}


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

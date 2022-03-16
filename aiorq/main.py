import json

from fastapi import FastAPI
from starlette.requests import Request

from connections import RedisSettings, create_pool
from jobs import Job

app = FastAPI()


@app.on_event("startup")
async def startup() -> None:
    app.state.redis = await create_pool(
        RedisSettings(
            host="127.0.0.1",
            port=6379,
            database=0,
            password=None
        )
    )


@app.get("/get_health_check")
async def get_health_check(request: Request, worker_name):
    result = await request.app.state.redis._get_health_check(worker_name=worker_name)
    return {"result": json.loads(result)}


@app.get("/enqueue_job_")
async def enqueue_job_(request: Request):
    job = await request.app.state.redis.enqueue_job('say_hello', name="wutong", _queue_name="aiorq:queue", _job_try=3)
    job_ = await job.info()
    return {"job_": job_}


@app.get("/index")
async def index(request: Request, queue_name="aiorq:queue"):
    functions = await request.app.state.redis.all_tasks()
    workers = await request.app.state.redis.all_workers()
    results = await request.app.state.redis.all_job_results()
    functions_num = len(list(functions))
    workers_num = len(list(workers))
    results_num = len(results)
    results = {"functions_num": functions_num, "workers_num": workers_num, "results_num": results_num}
    return {"results": results}


@app.get("/get_all_workers")
async def get_all_workers(request: Request):
    results = await request.app.state.redis.get_job_workers()
    results = [json.loads(v) for v in results]
    return {"results": results}


@app.get("/get_all_functions")
async def get_all_functions(request: Request):
    results = await request.app.state.redis.get_job_funcs()
    return {"results": results}


@app.get("/get_all_result")
async def get_all_result(request: Request, worker=None, task=None, job_id=None):
    all_result_ = await request.app.state.redis.all_job_results()
    if worker:
        all_result_ = [result_ for result_ in all_result_ if result_.get("worker_name") == worker]
    if task:
        all_result_ = [result_ for result_ in all_result_ if result_.get("function") == task]
    if job_id:
        all_result_ = [result_ for result_ in all_result_ if result_.get("job_id") == job_id]

    return {"results_": all_result_}


@app.get("/queued_jobs")
async def queued_jobs(request: Request, queue_name="aiorq:queue"):
    queued_jobs_ = await request.app.state.redis.queued_jobs(queue_name=queue_name)
    queued_jobs__ = []
    for queued_job_ in queued_jobs_:
        state = await Job(job_id=queued_job_.__dict__.get("job_id"), redis=request.app.state.redis,
                          _queue_name=queue_name).status()
        queued_job_.__dict__.update({"state": state})
        queued_jobs__.append(queued_job_)
    return {"queued_jobs__": queued_jobs__}


# job status
@app.get("/job_status")
async def job_status(request: Request, job_id="12673208ee3b417192b7cce06844adda", _queue_name="aiorq:queue"):
    job_status_ = await Job(job_id=job_id, redis=request.app.state.redis, _queue_name=_queue_name).info()
    return {"job_status_": job_status_}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app='main:app_server', host="127.0.0.1", port=9999, reload=True)

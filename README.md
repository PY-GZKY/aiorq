<h1 align="center">👽 Aiorq </h1>
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.7 | 3.8 | 3.9-blue" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/pypi-v0.29-red" />
</p>

## Introduction

Aiorq is a distributed task queue with asyncio and redis, which rewrite from arq to make improvement and include web
interface.

## Requirements

- redis >= 5.0
- aioredis>=1.1.0  <2.0.0

## Install

```shell
pip install aiorq
pip install aioredis
```

## Quick Start

### Task Definition

```python
# tasks.py
# -*- coding: utf-8 -*-

import asyncio
import os

from aiorq.connections import RedisSettings
from aiorq.cron import cron


async def say_hello(ctx, name) -> None:
    await asyncio.sleep(5)
    print(f"Hello {name}")


async def say_hi(ctx, name) -> None:
    await asyncio.sleep(3)
    print(f"Hi {name}")


async def startup(ctx):
    print("starting... done")


async def shutdown(ctx):
    print("ending... done")


async def run_cron(ctx, time_='2021-11-16 10:26:05'):
    print(time_)


class WorkerSettings:
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=os.getenv("REDIS_PORT", 6379),
        database=os.getenv("REDIS_DATABASE", 0),
        password=os.getenv("REDIS_PASSWORD", None)
    )

    functions = [say_hello, say_hi]

    on_startup = startup

    on_shutdown = shutdown

    cron_jobs = [
        cron(coroutine=run_cron, name="x100", minute=40, second=50, keep_result_forever=True)
    ]

    # allow_abort_jobs = True

    # worker_name = "ohuo"
    # queue_name = "ohuo"
```

### Run aiorq worker

```text
> aiorq tasks.WorkerSettings
15:08:50: Starting Queue: ohuo
15:08:50: Starting Worker: ohuo@04dce85c-1798-43eb-89d8-7c6d78919feb
15:08:50: Starting Functions: say_hello, EnHeng
15:08:50: redis_version=5.0.10 mem_usage=731.12K clients_connected=2 db_keys=9
starting...
```

## Integration in FastAPI

```python
# -*- coding: utf-8 -*-
import json
import os

from fastapi import FastAPI
from starlette.requests import Request

from aiorq.connections import RedisSettings, create_pool
from aiorq.jobs import Job

app = FastAPI()


@app.on_event("startup")
async def startup() -> None:
    app.state.redis = await create_pool(
        RedisSettings(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=os.getenv("REDIS_PORT", 6379),
            database=os.getenv("REDIS_DATABASE", 0),
            password=os.getenv("REDIS_PASSWORD", None)
        )
    )


@app.get("/get_health_check")
async def get_health_check(request: Request, worker_name):
    result = await request.app.state.redis._get_health_check(worker_name=worker_name)
    return {"result": json.loads(result)}


@app.get("/test")
async def t_(request: Request):
    job = await request.app.state.redis.enqueue_job('say_hello', name="wt", _queue_name="aiorq:queue", _job_try=5)
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
    results = {"functions_num": functions_num, "workers_num": workers_num, "results_num": results_num, }
    return {"results": results}


@app.get("/get_all_workers")
async def get_all_workers(request: Request, queue_name="aiorq:queue"):
    results = await request.app.state.redis.all_workers()
    results = [json.loads(v) for v in results]
    return {"results": results}


@app.get("/get_all_task")
async def get_all_task(request: Request):
    functions = await request.app.state.redis.all_tasks()
    results = [json.loads(v) for v in functions]
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


# job queued_jobs
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
    uvicorn.run(app='main:app', host="0.0.0.0", port=9999, reload=True)
```

## Thanks

- [Arq](https://github.com/samuelcolvin/arq) and [FastAPI](https://github.com/tiangolo/fastapi)

## License

[MIT](./LICENSE)





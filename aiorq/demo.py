# -*- coding: utf-8 -*-

import asyncio
import os
from unicodedata import name
from cron import cron
from connections import RedisSettings


async def say_hello(ctx, name) -> None:
    await asyncio.sleep(5)
    print(f"Hello {name}")


async def say_hi(ctx, name) -> None:
    await asyncio.sleep(10)
    print(f"Hi {name}")
    return name


async def startup(ctx):
    ...


async def shutdown(ctx):
    print("ending... done")



async def run_regularly(ctx,name_):
    print(f'run regularly {name_}')
    return f'hello {name_}'


class WorkerSettings:
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=os.getenv("REDIS_PORT", 6379),
        password=os.getenv("REDIS_PASSWORD", None),
        database=0,
    )

    functions = [say_hello, say_hi]

    cron_jobs = [
        cron(name="run_regularly_", coroutine=run_regularly, kwargs={"name_":"wutong"}, hour={17, 12, 18}, minute=50, keep_result_forever=True),
        # cron("demo.run_regularly", hour={15, 12, 18}, minute=50)
    ]

    on_startup = startup

    on_shutdown = shutdown

    allow_abort_jobs = True

    worker_name = "pai"

    queue_name = "pai:queue"

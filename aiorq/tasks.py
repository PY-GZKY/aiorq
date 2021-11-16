# -*- coding: utf-8 -*-

import asyncio
import os

from connections import RedisSettings
from cron import cron


async def say_hello(ctx, name) -> None:
    await asyncio.sleep(30)
    print(f"Hello {name}")


async def say_hi(ctx, name) -> None:
    await asyncio.sleep(3)
    print(f"Hi {name}")


async def startup(ctx):
    print("starting... done")


async def shutdown(ctx):
    print("ending... done")


async def run_cron(ctx,time_='2021-11-16 10:26:05'):
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

    allow_abort_jobs = True

    worker_name = "cp_1"
    # queue_name = "aiorq:queue1"

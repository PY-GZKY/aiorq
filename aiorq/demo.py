# -*- coding: utf-8 -*-

import asyncio
import os
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
    print("starting... done")


async def shutdown(ctx):
    print("ending... done")



async def run_regularly(ctx):
    print('run foo job at 9.12am, 12.12pm and 6.12pm')

class WorkerSettings:
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=os.getenv("REDIS_PORT", 6379),
        password=os.getenv("REDIS_PASSWORD", None),
        database=0,
    )

    functions = [say_hello, say_hi]

    cron_jobs = [
        cron(run_regularly, hour={17, 12, 18}, minute=12)
    ]

    on_startup = startup

    on_shutdown = shutdown

    allow_abort_jobs = True

    worker_name = "pai"

    queue_name = "pai:queue"

# -*- coding: utf-8 -*-

import asyncio

from cron import cron
from connections import RedisSettings


async def say_hello(ctx, name) -> None:
    await asyncio.sleep(3)
    print(f"Hello {name}")


async def say_hi(ctx, name) -> None:
    await asyncio.sleep(10)
    print(f"Hi {name}")


async def startup(ctx):
    print("starting... done")


async def shutdown(ctx):
    print("ending... done")



async def run_regularly(ctx):
    print('run foo job at 9.12am, 12.12pm and 6.12pm')


class WorkerSettings:
    redis_settings = RedisSettings(
        host="127.0.0.1",
        port=6379,
        database=0,
        password=None
    )

    functions = [say_hello, say_hi]

    cron_jobs = [
        cron(run_regularly, hour={17, 12, 18}, minute=12)
    ]

    on_startup = startup

    on_shutdown = shutdown

    allow_abort_jobs = True

    # keep_result_forever = True

    worker_name = "pai"

    queue_name = "pai:queue"

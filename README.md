<h1 align="center"> Aiorq </h1>
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.7 | 3.8 | 3.9 | 3.10-blue" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/pypi-v0.29-red" />
</p>

## Introduction

Aiorq is a distributed task queue with asyncio and redis, which rewrite from arq to make improvement and include web
interface.

See [documentation](https://aiorq.readthedocs.io) for more details.

## Requirements

- redis >= 5.0
- aioredis >= 2.0.0

## Install
~~pip install aiorq~~

<!-- ```shell
pip install aioredis
``` -->

## Quick Start

### Task Definition

```python
# demo.py
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

## Dashboard
- fastapi >= 0.5.0
- motor >= 2.0.0

See [aiorq dashboard](https://github.com/PY-GZKY/aiorq-dashboard) for more details.
 

## Thanks

- [Arq](https://github.com/samuelcolvin/arq) and [FastAPI](https://github.com/tiangolo/fastapi)

## License

[MIT](./LICENSE)





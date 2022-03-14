# [Aiorq](https://github.com/PY-GZKY/aiorq)
<h1 align="center">Aiorq</h1>
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.7 | 3.8 | 3.9-blue" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/pypi-v0.33-red" />
</p>

`Aiorq` 是一个包含 `asyncio` 和 `redis` 的分布式任务队列，它从 `arq` 重写以进行改进，并包含 `web` 接口。



#### 异步的
`aiorq` 继承了 `arq` 库的基础功能。

由 `python3` 的 `asyncio` 构建的，允许非阻塞作业排队和执行。可以使用`asyncio` 池同时运行多个作业（可能有数百个）`Tasks`。
延迟执行、轻松重试作业和悲观执行（见下文）意味着非常适合必须完成的关键作业。

#### 强大的
`aiorq` 对比 `arq` 原生新增储存了 `Worker` 进程工人信息和所属队列关系和任务信息于 `redis` 数据库。

我总是认为`分布式队列`的基础单元应该是 `工人进程`(我认为`arq`在这方面可能想做的更为简洁, 而如果要提供`可视化ui` 工人进程就是比较恰当的选择, 就像 `flower` 那样)



#### 快速而轻量的
目前 `aiorq` 只有大约 `750` 行，不会有太大变化。 `aiorq` 被设计得更简单、更清晰、更强大。



## 依赖

- `redis >= 5.0`
- `aioredis>=1.1.0  <2.0.0`

#### 安装

```shell
pip install aiorq
pip install aioredis
```

## 用法
#### 快速开始
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

    functions = [say_hello, say_hi, run_cron]

    on_startup = startup

    on_shutdown = shutdown

    cron_jobs = [
        cron(coroutine=run_cron, name="x100", minute=40, second=50, keep_result_forever=True)
    ]

    # allow_abort_jobs = True

    # worker_name = "ohuo"
    # queue_name = "ohuo"
```
以 `tasks.py` 文件为例，文件中声明了 `say_hello`、 `say_hi`、 `run_cron` 方法、其中 
`run_cron` 作为定时任务。

#### 健康检查

#### 重试作业和取消

#### 获取结果和状态

#### 启动 Worker

```shell
> aiorq tasks.WorkerSettings
15:08:50: Starting Queue: ohuo
15:08:50: Starting Worker: ohuo@04dce85c-1798-43eb-89d8-7c6d78919feb
15:08:50: Starting Functions: say_hello
15:08:50: redis_version=5.0.10 mem_usage=731.12K clients_connected=2 db_keys=9
starting...
```

#### 关于命令行
```shell
aiorq --help
arq --check demo.WorkerSettings
```

#### 如何优雅的杀死 Worker 进程
> 需要注意的是，当 `worker` 后台常驻的时候(可能是 `nohup` 或者 `supervisor`)，使用 `kill -9` 强制终端信号的时候，很有可能无法执行 `redis` 会话的 `close()` 回调。
这跟 `ctrl + c` 中断信号是非一致的，比较推荐的做法是使用 `kill -15` 优雅的阻塞等待任务完成后杀死进程。这可能作为一个 `Fix` 在下一个版本中修复、唉。

#### Reference
```shell

```

## 致谢

- [Arq](https://github.com/samuelcolvin/arq) and [FastAPI](https://github.com/tiangolo/fastapi)

## License

[MIT]()

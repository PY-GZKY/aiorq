import asyncio
import functools

import msgpack
import pytest
from aioredis import create_redis_pool

from aiorq.connections import AioRedis, create_pool
from aiorq.worker import Worker


@pytest.yield_fixture
async def aio_redis(loop):
    redis_ = await create_redis_pool(
        ('localhost', 6379), encoding='utf8', loop=loop, commands_factory=AioRedis, minsize=5
    )
    await redis_.flushall()
    yield redis_
    redis_.close()
    await redis_.wait_closed()


@pytest.yield_fixture
async def aio_redis_msgpack(loop):
    redis_ = await create_redis_pool(
        ('localhost', 6379),
        encoding='utf8',
        loop=loop,
        commands_factory=functools.partial(
            AioRedis, job_serializer=msgpack.packb, job_deserializer=functools.partial(msgpack.unpackb, raw=False)
        ),
    )
    await redis_.flushall()
    yield redis_
    redis_.close()
    await redis_.wait_closed()


@pytest.yield_fixture
async def worker(aio_redis):
    worker_: Worker = None

    def create(functions=[], burst=True, poll_delay=0, max_jobs=10, aio_redis=aio_redis, **kwargs):
        nonlocal worker_
        worker_ = Worker(
            functions=functions, redis_pool=aio_redis, burst=burst, poll_delay=poll_delay, max_jobs=max_jobs, **kwargs
        )
        return worker_

    yield create

    if worker_:
        await worker_.close()


@pytest.fixture(name='create_pool')
async def fix_create_pool(loop):
    pools = []

    async def create_pool_(settings, *args, **kwargs):
        pool = await create_pool(settings, *args, **kwargs)
        pools.append(pool)
        return pool

    yield create_pool_

    for p in pools:
        p.close()

    await asyncio.gather(*[p.wait_closed() for p in pools])

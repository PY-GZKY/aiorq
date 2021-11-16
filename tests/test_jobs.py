import asyncio
import pickle

import pytest
from pytest_toolbox.comparison import CloseToNow

from aiorq import Worker, func
from aiorq.connections import AioRedis, RedisSettings, create_pool
from aiorq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix, result_key_prefix
from aiorq.jobs import DeserializationError, Job, JobResult, JobStatus, deserialize_job_raw, serialize_result


async def test_job_in_progress(aio_redis: AioRedis):
    await aio_redis.set(in_progress_key_prefix + 'foobar', b'1')
    j = Job('foobar', aio_redis)
    assert JobStatus.in_progress == await j.status()
    assert str(j) == '<aiorq job foobar>'


async def test_unknown(aio_redis: AioRedis):
    j = Job('foobar', aio_redis)
    assert JobStatus.not_found == await j.status()
    info = await j.info()
    assert info is None


async def test_result_timeout(aio_redis: AioRedis):
    j = Job('foobar', aio_redis)
    with pytest.raises(asyncio.TimeoutError):
        await j.result(0.1, poll_delay=0)


async def test_enqueue_job(aio_redis: AioRedis, worker, queue_name=default_queue_name):
    async def foobar(ctx, *args, **kwargs):
        return 42

    j = await aio_redis.enqueue_job('foobar', 1, 2, c=3, _queue_name=queue_name)
    assert isinstance(j, Job)
    assert JobStatus.queued == await j.status()
    worker: Worker = worker(functions=[func(foobar, name='foobar')], queue_name=queue_name)
    await worker.main()
    r = await j.result(poll_delay=0)
    assert r == 42
    assert JobStatus.complete == await j.status()
    info = await j.info()
    expected_queue_name = queue_name or aio_redis.default_queue_name
    assert info == JobResult(
        job_try=1,
        function='foobar',
        args=(1, 2),
        kwargs={'c': 3},
        enqueue_time=CloseToNow(),
        success=True,
        result=42,
        start_time=CloseToNow(),
        finish_time=CloseToNow(),
        score=None,
        queue_name=expected_queue_name,
    )
    results = await aio_redis.all_job_results()
    assert results == [
        JobResult(
            function='foobar',
            args=(1, 2),
            kwargs={'c': 3},
            job_try=1,
            enqueue_time=CloseToNow(),
            success=True,
            result=42,
            start_time=CloseToNow(),
            finish_time=CloseToNow(),
            score=None,
            queue_name=expected_queue_name,
            job_id=j.job_id,
        )
    ]


async def test_enqueue_job_alt_queue(aio_redis: AioRedis, worker):
    await test_enqueue_job(aio_redis, worker, queue_name='custom_queue')


async def test_enqueue_job_nondefault_queue(worker):
    """Test initializing aio_redis with a queue name, and the worker using it."""
    aio_redis = await create_pool(RedisSettings(), default_queue_name='test_queue')
    await test_enqueue_job(
        aio_redis,
        lambda functions, **_: worker(functions=functions, aio_redis=aio_redis, queue_name=None),
        queue_name=None,
    )


async def test_cant_unpickle_at_all():
    class Foobar:
        def __getstate__(self):
            raise TypeError("this doesn't pickle")

    r1 = serialize_result('foobar', (1,), {}, 1, 123, True, Foobar(), 123, 123, 'testing', 'test-queue')
    assert isinstance(r1, bytes)
    r2 = serialize_result('foobar', (Foobar(),), {}, 1, 123, True, Foobar(), 123, 123, 'testing', 'test-queue')
    assert r2 is None


async def test_custom_serializer():
    class Foobar:
        def __getstate__(self):
            raise TypeError("this doesn't pickle")

    def custom_serializer(x):
        return b'0123456789'

    r1 = serialize_result(
        'foobar', (1,), {}, 1, 123, True, Foobar(), 123, 123, 'testing', 'test-queue', serializer=custom_serializer
    )
    assert r1 == b'0123456789'
    r2 = serialize_result(
        'foobar',
        (Foobar(),),
        {},
        1,
        123,
        True,
        Foobar(),
        123,
        123,
        'testing',
        'test-queue',
        serializer=custom_serializer,
    )
    assert r2 == b'0123456789'


async def test_deserialize_result(aio_redis: AioRedis, worker):
    async def foobar(ctx, a, b):
        return a + b

    j = await aio_redis.enqueue_job('foobar', 1, 2)
    assert JobStatus.queued == await j.status()
    worker: Worker = worker(functions=[func(foobar, name='foobar')])
    await worker.run_check()
    assert await j.result(poll_delay=0) == 3
    assert await j.result(poll_delay=0) == 3
    info = await j.info()
    assert info.args == (1, 2)
    await aio_redis.set(result_key_prefix + j.job_id, b'invalid pickle data')
    with pytest.raises(DeserializationError, match='unable to deserialize job result'):
        assert await j.result(poll_delay=0) == 3


async def test_deserialize_info(aio_redis: AioRedis):
    j = await aio_redis.enqueue_job('foobar', 1, 2)
    assert JobStatus.queued == await j.status()
    await aio_redis.set(job_key_prefix + j.job_id, b'invalid pickle data')

    with pytest.raises(DeserializationError, match='unable to deserialize job'):
        assert await j.info()


async def test_deserialize_job_raw():
    assert deserialize_job_raw(pickle.dumps({'f': 1, 'a': 2, 'k': 3, 't': 4, 'et': 5})) == (1, 2, 3, 4, 5)
    with pytest.raises(DeserializationError, match='unable to deserialize job'):
        deserialize_job_raw(b'123')


async def test_get_job_result(aio_redis: AioRedis):
    with pytest.raises(KeyError, match='job "foobar" not found'):
        await aio_redis._get_job_result('foobar')


async def test_result_pole_delay_dep(aio_redis: AioRedis):
    j = Job('foobar', aio_redis)
    r = serialize_result('foobar', (1,), {}, 1, 123, True, 42, 123, 123, 'testing', 'test-queue')
    await aio_redis.set(result_key_prefix + j.job_id, r)
    with pytest.warns(
        DeprecationWarning, match='"pole_delay" is deprecated, use the correct spelling "poll_delay" instead'
    ):
        assert await j.result(pole_delay=0) == 42

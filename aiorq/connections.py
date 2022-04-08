import asyncio
import functools
import json
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from operator import attrgetter
from typing import Any, Callable, Generator, List, Optional, Tuple, Union, Dict
from urllib.parse import urlparse
from uuid import uuid4

from aioredis import Redis, ConnectionPool
from aioredis.exceptions import RedisError, WatchError
from aioredis.sentinel import Sentinel
from pydantic.validators import make_arbitrary_type_validator

from .constants import default_queue_name, default_worker_name, job_key_prefix, result_key_prefix, worker_key, \
    health_check_key_suffix, func_key
from .jobs import Job
from .serialize import Deserializer, Serializer, deserialize_job, serialize_job, deserialize_func, deserialize_worker
from .specs import JobDef, JobResult
from .utils import timestamp_ms, to_ms, to_unix_ms, ms_to_datetime

logger = logging.getLogger('aiorq.connections')


class SSLContext(ssl.SSLContext):
    """
    是否 ssl
    """

    @classmethod
    def __get_validators__(cls) -> Generator[Callable[..., Any], None, None]:
        yield make_arbitrary_type_validator(ssl.SSLContext)


@dataclass
class RedisSettings:
    """
    No-Op class used to hold redis connection redis_settings.

    Used by :func:`aiorq.connections.create_pool` and :class:`aiorq.worker.Worker`.
    """

    host: Union[str, List[Tuple[str, int]]] = 'localhost'
    port: int = 6379
    database: int = 0
    password: Optional[str] = None
    ssl: Union[bool, None, SSLContext] = None
    conn_timeout: int = 1
    conn_retries: int = 5
    conn_retry_delay: int = 1

    sentinel: bool = False
    sentinel_master: str = 'mymaster'

    @classmethod
    def from_dsn(cls, dsn: str) -> 'RedisSettings':
        conf = urlparse(dsn)
        assert conf.scheme in {'redis', 'rediss'}, 'invalid DSN scheme'
        return RedisSettings(
            host=conf.hostname or 'localhost',
            port=conf.port or 6379,
            ssl=conf.scheme == 'rediss',
            password=conf.password,
            database=int((conf.path or '0').strip('/')),
        )

    def __repr__(self) -> str:
        return f"RedisSettings({', '.join((f'{k}={v!r}' for k, v in self.__dict__.items()))})"


# extra time after the job is expected to start when the job key should expire, 1 day in ms
expires_extra_ms = 86_400_000


class AioRedis(Redis):  # type: ignore
    """
    :param redis_settings: 一个实例。连接。重新定义设置。
    :param job_serializer:将Python对象序列化为字节的函数,默认为pickle。
    :param job_反序列化器:将字节反序列化为Python对象的函数,默认为pickle。
    :param default_queue_name:要使用的默认队列名称。
    :param kwargs:关键字参数
    """

    def __init__(
            self,
            pool_or_conn: Optional[ConnectionPool] = None,
            job_serializer: Optional[Serializer] = None,
            job_deserializer: Optional[Deserializer] = None,
            default_queue_name: str = default_queue_name,
            default_worker_name: str = default_worker_name,
            **kwargs: Any,
    ) -> None:
        self.job_serializer = job_serializer
        self.job_deserializer = job_deserializer
        self.queue_name = default_queue_name
        self.worker_name = default_worker_name
        if pool_or_conn:
            kwargs['connection_pool'] = pool_or_conn
        super().__init__(**kwargs)

    # 任务加入 redis 队列
    async def enqueue_job(
            self,
            function: str,
            *args: Any,
            job_id: Optional[str] = None,
            queue_name: Optional[str] = None,
            defer_until: Optional[datetime] = None,
            defer_by: Union[None, int, float, timedelta] = None,
            expires: Union[None, int, float, timedelta] = None,
            job_try: Optional[int] = None,
            **kwargs: Any,
    ) -> Optional[Job]:
        """
        Enqueue a job.
        :param function:要调用的函数的名称
        :param args:传递给函数的参数
        :param _job_id:作业的id,可用于强制作业唯一性
        :param _queue_name:作业的队列,可用于在不同队列中创建作业
        :param _defer_直到:运行作业的日期时间
        :param _defer_by:运行作业前等待的持续时间
        :param _expires:如果作业在此持续时间之后仍未启动,请不要运行它
        :param _job_try:在作业中重新排队作业时非常有用
        :param kwargs:传递给函数的任何关键字参数
        """
        # 如果 队列名称为 空使用默认名称
        if queue_name is None:
            queue_name = self.queue_name
        job_id = job_id or uuid4().hex
        job_key = job_key_prefix + job_id
        assert not (defer_until and defer_by), "use either 'defer_until' or 'defer_by' or neither, not both"

        defer_by_ms = to_ms(defer_by)
        expires_ms = to_ms(expires)

        # self 代表类 redis 链接类
        async with self.pipeline(transaction=True) as pipe:
            # 管道
            await pipe.unwatch()
            await pipe.watch(job_key)
            # 是否存在该键
            job_exists = pipe.exists(job_key)
            job_result_exists = pipe.exists(result_key_prefix + job_id)
            # 执行器
            await pipe.execute()
            if await job_exists or await job_result_exists:
                return None

            # score 是运行任务的时间
            enqueue_time_ms = timestamp_ms()
            if defer_until is not None:
                score = to_unix_ms(defer_until)
            elif defer_by_ms:
                score = enqueue_time_ms + defer_by_ms
            else:
                score = enqueue_time_ms

            expires_ms = expires_ms or score - enqueue_time_ms + expires_extra_ms

            job = serialize_job(function, args, kwargs, job_try, enqueue_time_ms, queue_name,
                                serializer=self.job_serializer)

            # redis 批处理执行 添加任务id到 redis 队列
            pipe.multi()

            # 如果到达 expires_ms 这个时间还未执行 redis 超市删除key 即任务取消运行
            pipe.psetex(job_key, expires_ms, job)
            pipe.zadd(queue_name, {job_id: score})
            try:
                await pipe.execute()
            except WatchError:
                # job got enqueued since we checked 'job_exists'
                return None
        return Job(job_id, redis=self, _queue_name=queue_name, _deserializer=self.job_deserializer)

    # 根据 key 获取工作结果
    async def _get_job_result(self, key: bytes) -> JobResult:
        # 获取组合键的后半部分
        job_id = key[len(result_key_prefix):]
        job_id = job_id.decode()
        job = Job(job_id, self, _deserializer=self.job_deserializer)
        r = await job.result_info()
        if r is None:
            raise KeyError(f'job "{key}" not found')
        r.job_id = job_id
        return r

    async def all_job_results(self) -> List[JobResult]:
        """
        获取所有工作结果
        """
        keys = await self.keys(f'{result_key_prefix}*')
        results = await asyncio.gather(*[self._get_job_result(k) for k in keys])
        return sorted(results, key=attrgetter('enqueue_time'))

    async def get_job_funcs(self) -> List[Dict]:
        """
        """
        v = await self.get(func_key)
        return deserialize_func(v)

    async def get_job_workers(self) -> List[Dict]:
        """
        """
        keys = await self.keys(f'{worker_key}*')
        workers_ = []
        for key_ in keys:
            v = await self.get(key_)
            dw_ = deserialize_worker(v)
            dw_.health_check = await self._get_health_check(dw_.worker_name)
            workers_.append(dw_)
        return workers_

    async def _get_health_check(self, worker_name: str) -> Dict:
        v = await self.get(f"{health_check_key_suffix}{worker_name}")
        return json.loads(v) if v else {}

    async def _get_job_def(self, job_id: bytes, queue_name: str, score: int) -> JobDef:
        job_id_ = job_id.decode()
        v = await self.get(job_key_prefix + job_id_)
        jd = deserialize_job(v, deserializer=self.job_deserializer)
        j = Job(job_id=job_id_, redis=self, _queue_name=queue_name)
        state = await j.status()
        # print("ms_to_datetime(score): ",ms_to_datetime(score))
        jd.score = score
        jd.job_id = job_id_
        jd.start_time = ms_to_datetime(score)
        jd.state = state
        jd.queue_name = queue_name
        jd.worker_name = self.worker_name
        print(jd)
        return jd

    async def queued_jobs(self, *, queue_name: str = default_queue_name) -> List[JobDef]:
        """
        Get information about queued, mostly useful when testing.
        """
        jobs = await self.zrange(queue_name, withscores=True, start=0, end=-1)
        return await asyncio.gather(*[self._get_job_def(job_id, queue_name, int(score)) for job_id, score in jobs])

    async def redis_info(self) -> Dict[str, Any]:
        return await self.info()


async def create_pool(
        settings_: RedisSettings = None,
        *,
        retry: int = 0,
        job_serializer: Optional[Serializer] = None,
        job_deserializer: Optional[Deserializer] = None,
        default_queue_name: str = default_queue_name,
) -> AioRedis:
    """
    Create a new redis pool, retrying up to ``conn_retries`` times if the connection fails.
    Returns a :class:`arq.connections.ArqRedis` instance, thus allowing job enqueuing.
    """
    settings: RedisSettings = RedisSettings() if settings_ is None else settings_

    assert not (
            type(settings.host) is str and settings.sentinel
    ), "str provided for 'host' but 'sentinel' is true; list of sentinels expected"

    if settings.sentinel:
        def pool_factory(*args: Any, **kwargs: Any) -> AioRedis:
            client = Sentinel(*args, sentinels=settings.host, ssl=settings.ssl, **kwargs)
            return client.master_for(settings.sentinel_master, redis_class=AioRedis)

    else:
        """
        from urllib.parse import quote
        redis_uri = f"redis://:{quote(settings.password)}@{settings.host}:{settings.port}/{settings.database}"
        pool_or_conn = aioredis.from_url(
            redis_uri, decode_responses=True
        )
        """
        pool_factory = functools.partial(
            AioRedis,
            host=settings.host,
            port=settings.port,
            socket_connect_timeout=settings.conn_timeout,
            ssl=settings.ssl
        )

    try:
        pool = pool_factory(db=settings.database, password=settings.password, encoding='utf8')
        pool.job_serializer = job_serializer
        pool.job_deserializer = job_deserializer
        pool.default_queue_name = default_queue_name
        await pool.ping()  # ping

    except (ConnectionError, OSError, RedisError, asyncio.TimeoutError) as e:
        if retry < settings.conn_retries:
            logger.warning(
                'redis connection error %s:%s %s %s, %d retries remaining...',
                settings.host,
                settings.port,
                e.__class__.__name__,
                e,
                settings.conn_retries - retry,
            )
            await asyncio.sleep(settings.conn_retry_delay)
        else:
            raise
    else:
        if retry > 0:
            logger.info('redis connection successful')
        return pool

    # recursively attempt to create the pool outside the except block to avoid
    # "During handling of the above exception..." madness
    return await create_pool(
        settings,
        retry=retry + 1,
        job_serializer=job_serializer,
        job_deserializer=job_deserializer,
        default_queue_name=default_queue_name,
    )


async def log_redis_info(redis: Redis, log_func: Callable[[str], Any]) -> None:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.info(section='Server')
        pipe.info(section='Memory')
        pipe.info(section='Clients')
        pipe.dbsize()
        info_server, info_memory, info_clients, key_count = await pipe.execute()

    redis_version = info_server.get('redis_version', '?')
    mem_usage = info_memory.get('used_memory_human', '?')
    clients_connected = info_clients.get('connected_clients', '?')

    log_func(
        f'redis_version={redis_version} '
        f'mem_usage={mem_usage} '
        f'clients_connected={clients_connected} '
        f'db_keys={key_count}'
    )

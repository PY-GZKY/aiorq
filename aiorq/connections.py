import asyncio
import functools
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from operator import attrgetter
from typing import Any, Callable, Generator, List, Optional, Tuple, Union, Dict
from urllib.parse import urlparse
from uuid import uuid4

import aioredis
from aioredis import MultiExecError, Redis
from pydantic.validators import make_arbitrary_type_validator

from aiorq.constants import default_queue_name, default_worker_name, job_key_prefix, result_key_prefix, worker_key, \
    task_key, \
    health_check_key_suffix
from aiorq.jobs import Deserializer, Job, JobDef, JobResult, Serializer, deserialize_job, serialize_job
from aiorq.utils import timestamp_ms, to_ms, to_unix_ms

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
        return 'RedisSettings({})'.format(', '.join(f'{k}={v!r}' for k, v in self.__dict__.items()))


# extra time after the job is expected to start when the job key should expire, 1 day in ms
expires_extra_ms = 86_400_000


class AioRedis(Redis):  # type: ignore
    """
    “`aioredis”的一个小类。Redis``增加了：func:`aiorq。连接。排队等待工作`。
    ：param redis_settings:“`aiorq”的一个实例。连接。重新定义设置``。
    ：param job_serializer：将Python对象序列化为字节的函数，默认为pickle。倾倒
    ：param job_反序列化器：将字节反序列化为Python对象的函数，默认为pickle。荷载
    ：param default_queue_name：要使用的默认队列名称，默认为``aiorq。排队``。
    ：param kwargs：直接传递给``aioredis的关键字参数。Redis``。
    """

    def __init__(
            self,
            pool_or_conn: Any,
            job_serializer: Optional[Serializer] = None,
            job_deserializer: Optional[Deserializer] = None,
            default_queue_name: str = default_queue_name,
            default_worker_name: str = default_worker_name,
            **kwargs: Any,
    ) -> None:
        self.job_serializer = job_serializer
        self.job_deserializer = job_deserializer
        self.default_queue_name = default_queue_name
        self.default_worker_name = default_worker_name
        super().__init__(pool_or_conn, **kwargs)

    # 任务加入 redis 队列
    async def enqueue_job(
            self,
            function: str,
            *args: Any,
            _job_id: Optional[str] = None,
            _queue_name: Optional[str] = None,
            _defer_until: Optional[datetime] = None,
            _defer_by: Union[None, int, float, timedelta] = None,
            _expires: Union[None, int, float, timedelta] = None,
            _job_try: Optional[int] = None,
            **kwargs: Any,
    ) -> Optional[Job]:
        """
        Enqueue a job.

        ：param function:要调用的函数的名称
        ：param args：传递给函数的参数
        ：param _job_id：作业的id，可用于强制作业唯一性
        ：param _queue_name：作业的队列，可用于在不同队列中创建作业
        ：param _defer_直到：运行作业的日期时间
        ：param _defer_by:运行作业前等待的持续时间
        ：param _expires：如果作业在此持续时间之后仍未启动，请不要运行它
        ：param _job_try：在作业中重新排队作业时非常有用
        ：param kwargs：传递给函数的任何关键字参数
        ：return：：class:`aiorq。乔布斯。Job`instance或`None``如果具有此ID的作业已存在
        """
        # 如果 队列名称为 空使用默认名称
        if _queue_name is None:
            _queue_name = self.default_queue_name
        job_id = _job_id or uuid4().hex
        job_key = job_key_prefix + job_id
        assert not (_defer_until and _defer_by), "use either 'defer_until' or 'defer_by' or neither, not both"

        defer_by_ms = to_ms(_defer_by)
        expires_ms = to_ms(_expires)

        # self 代表类 redis 链接类
        with await self as conn:
            # aioredis 管道
            pipe = conn.pipeline()
            pipe.unwatch()
            pipe.watch(job_key)
            # 是否存在该键
            job_exists = pipe.exists(job_key)
            job_result_exists = pipe.exists(result_key_prefix + job_id)
            # 执行器
            await pipe.execute()
            if await job_exists or await job_result_exists:
                return None

            enqueue_time_ms = timestamp_ms()
            if _defer_until is not None:
                score = to_unix_ms(_defer_until)
            elif defer_by_ms:
                score = enqueue_time_ms + defer_by_ms
            else:
                score = enqueue_time_ms

            expires_ms = expires_ms or score - enqueue_time_ms + expires_extra_ms

            job = serialize_job(function, args, kwargs, _job_try, enqueue_time_ms, _queue_name,
                                serializer=self.job_serializer)

            # redis 批处理执行
            tr = conn.multi_exec()

            # 添加任务id到 redis 队列
            tr.psetex(job_key, expires_ms, job)
            tr.zadd(_queue_name, score, job_id)
            try:
                await tr.execute()
            except MultiExecError:
                # job got enqueued since we checked 'job_exists'
                await asyncio.gather(*tr._results, return_exceptions=True)
                return None
        return Job(job_id, redis=self, _queue_name=_queue_name, _deserializer=self.job_deserializer)

    # 根据 key 获取工作结果
    async def _get_job_result(self, key: str) -> JobResult:
        # 获取组合键的后半部分
        job_id = key[len(result_key_prefix):]
        job = Job(job_id, self, _deserializer=self.job_deserializer)
        r = await job.result_info()
        if r is None:
            raise KeyError(f'job "{key}" not found')
        # 附上 job_id
        r.job_id = job_id
        return r

    async def all_job_results(self) -> List[JobResult]:
        """
        获取所有工作结果
        """
        keys = await self.keys(result_key_prefix + '*')
        results = await asyncio.gather(*[self._get_job_result(k) for k in keys])
        return sorted(results, key=attrgetter('enqueue_time'))

    async def all_tasks(self) -> List[Dict]:
        """
        获取所有任务方法
        """
        v = await self.get(task_key, encoding=None)
        return v.decode()

    async def all_workers(self) -> List[Dict]:
        """
        获取所有工作者
        """
        keys = await self.keys(worker_key + '*')
        workers_ = []
        for key_ in keys:
            v = await self.get(key_, encoding=None)
            workers_.append(v.decode())
        return workers_

    # 获取健康检查结果
    async def _get_health_check(self, worker_name: str) -> Dict:
        v = await self.get(f"{health_check_key_suffix}{worker_name}", encoding=None)
        return v

    async def _get_job_def(self, job_id: str, score: int) -> JobDef:
        v = await self.get(job_key_prefix + job_id, encoding=None)
        jd = deserialize_job(v, deserializer=self.job_deserializer)
        jd.score = score
        jd.job_id = job_id
        return jd

    # 获取正在等待队列中的任务
    async def queued_jobs(self, *, queue_name: str = default_queue_name) -> List[JobDef]:
        """
        Get information about queued, mostly useful when testing.
        """
        jobs = await self.zrange(queue_name, withscores=True)
        return await asyncio.gather(*[self._get_job_def(job_id, score) for job_id, score in jobs])


# 创建 redis 连接池 返回 AioRedis
async def create_pool(
        settings_: RedisSettings = None,
        *,
        retry: int = 0,
        job_serializer: Optional[Serializer] = None,
        job_deserializer: Optional[Deserializer] = None,
        default_queue_name: str = default_queue_name,
) -> AioRedis:
    """
    创建一个新的redis池，如果连接失败，最多重试“conn_retries”次。
    类似于“aioredis”。创建_redis_pool``除非它返回一个：class:`aiorq。连接。
    从而允许工作排队。
    """
    settings: RedisSettings = RedisSettings() if settings_ is None else settings_

    assert not (
            type(settings.host) is str and settings.sentinel
    ), "str provided for 'host' but 'sentinel' is true; list of sentinels expected"

    if settings.sentinel:
        addr: Any = settings.host

        async def pool_factory(*args: Any, **kwargs: Any) -> Redis:
            client = await aioredis.sentinel.create_sentinel_pool(*args, ssl=settings.ssl, **kwargs)
            return client.master_for(settings.sentinel_master)

    else:
        pool_factory = functools.partial(
            aioredis.create_pool, create_connection_timeout=settings.conn_timeout, ssl=settings.ssl
        )
        addr = settings.host, settings.port

    try:
        # 创建 redis 池
        pool = await pool_factory(addr, db=settings.database, password=settings.password, encoding='utf8')
        pool = AioRedis(
            pool,
            job_serializer=job_serializer,
            job_deserializer=job_deserializer,
            default_queue_name=default_queue_name,
        )

    except (ConnectionError, OSError, aioredis.RedisError, asyncio.TimeoutError) as e:
        if retry < settings.conn_retries:
            logger.warning(
                'redis connection error %s %s %s, %d retries remaining...',
                addr,
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

    # 递归地尝试在except块之外创建池以避免“在处理上述异常时……”疯狂
    return await create_pool(
        settings,
        retry=retry + 1,
        job_serializer=job_serializer,
        job_deserializer=job_deserializer,
        default_queue_name=default_queue_name,
    )

# 日志方法
async def log_redis_info(redis: Redis, log_func: Callable[[str], Any]) -> None:
    with await redis as r:
        # 获取 redis 服务 内存 客户端 键的个数 数据库大小
        info_server, info_memory, info_clients, key_count = await asyncio.gather(
            r.info(section='Server'), r.info(section='Memory'), r.info(section='Clients'), r.dbsize(),
        )

    redis_version = info_server.get('server', {}).get('redis_version', '?')
    mem_usage = info_memory.get('memory', {}).get('used_memory_human', '?')
    clients_connected = info_clients.get('clients', {}).get('connected_clients', '?')

    log_func(
        f'redis_version={redis_version} '
        f'mem_usage={mem_usage} '
        f'clients_connected={clients_connected} '
        f'db_keys={key_count}'
    )

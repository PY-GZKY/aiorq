import asyncio
import inspect
import json
import logging
import os
import signal
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from signal import Signals
from time import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union, cast

from aioredis.exceptions import ResponseError, WatchError
from pydantic.utils import import_string
import dataclasses
from specs import JobFunc
from connections import RedisSettings, create_pool, log_redis_info, AioRedis
from constants import (
    abort_job_max_age,
    abort_jobs_ss,
    default_queue_name,
    health_check_key_suffix,
    in_progress_key_prefix,
    job_key_prefix,
    keep_cronjob_progress,
    result_key_prefix,
    retry_key_prefix,
    worker_key,
    worker_key_close_expire,
    default_worker_name,
    func_key
)
from cron import CronJob
from exception import FailedJobs, Retry, JobExecutionFailed, RetryJob, SerializationError
from serialize import Serializer, Deserializer, deserialize_job_raw, serialize_result
from utils import args_to_string, ms_to_datetime, poll, timestamp_ms, to_ms, to_seconds, to_unix_ms, truncate
from version import __version__
from specs import JobWorker

if TYPE_CHECKING:
    from typing_ import SecondsTimedelta, StartupShutdown, WorkerCoroutine, WorkerSettingsType  # noqa F401

logger = logging.getLogger('aiorq.worker')
no_result = object()


@dataclass
class Function:
    name: str
    coroutine: 'WorkerCoroutine'
    timeout_s: Optional[float]
    keep_result_s: Optional[float]
    keep_result_forever: Optional[bool]
    max_tries: Optional[int]


def func(
        coroutine: Union[str, Function, 'WorkerCoroutine'],
        *,
        name: Optional[str] = None,
        keep_result: Optional['SecondsTimedelta'] = None,
        timeout: Optional['SecondsTimedelta'] = None,
        keep_result_forever: Optional[bool] = None,
        max_tries: Optional[int] = None,
) -> Function:
    """
    Wrapper for a job function which lets you configure more settings.
    :param coroutine: coroutine function to call, can be a string to import
    :param name: name for function, if None, ``coroutine.__qualname__`` is used
    :param keep_result: duration to keep the result for, if 0 the result is not kept
    :param keep_result_forever: whether to keep results forever, if None use Worker default, wins over ``keep_result``
    :param timeout: maximum time the job should take
    :param max_tries: maximum number of tries allowed for the function, use 1 to prevent retrying
    """
    if isinstance(coroutine, Function):
        return coroutine

    if isinstance(coroutine, str):
        name = name or coroutine
        coroutine_: 'WorkerCoroutine' = import_string(coroutine)
    else:
        coroutine_ = coroutine

    assert asyncio.iscoroutinefunction(coroutine_), f'{coroutine_} is not a coroutine function'
    timeout = to_seconds(timeout)
    keep_result = to_seconds(keep_result)
    return Function(name or coroutine_.__qualname__, coroutine_, timeout, keep_result, keep_result_forever, max_tries)


class Worker:
    """
    :param functions:要注册的函数列表,可以是原始协同例程函数。
    :param queue_name:从中获取作业的队列名称
    :param cron_jobs:要运行的cron jobs列表
    :param redis_settings:用于创建redis连接的设置
    :param redis_pool:现有redis pool,通常无
    :param burst:所有作业运行后是否停止工作进程
    :param on_startup:coroutine函数在启动时运行
    :param on_shutdown:关闭时运行的协同程序功能
    :param handle_signals:默认为true,寄存器信号处理程序,在其他异步框架内运行时设置为false
    :param max_jobs:一次运行的最大作业数
    :param job_timeout:默认作业超时（最大运行时间）
    :param keep_result:保留作业结果的默认持续时间
    :参数永远保存结果:是否永远保存结果
    :param poll_delay:轮询队列以获取新作业之间的持续时间
    :param queue_read_limit:每次轮询队列时从队列中提取的最大作业数；默认情况下等于“最大工作”``
    :param max_tries:默认重试作业的最大次数
    :param health_check_interval:设置健康检查键的频率
    :param health_check_key:设置健康检查的redis键
    :param ctx:保存额外用户定义状态的字典
    :param retry_jobs:是否在重试时重试作业或取消错误
    :param allow_abort_jobs:是否在调用:func:aiorq时中止作业。乔布斯。工作流产
    :param max_burst_jobs:在突发模式下要处理的最大作业数（使用负值禁用）
    :param job_serializer:将Python对象序列化为字节的函数,默认为pickle。倾倒
    :param job_deserializer:将字节反序列化为Python对象的函数,默认为pickle。荷载
    """

    def __init__(
            self,
            functions: Sequence[Union[Function, 'WorkerCoroutine']] = (),
            *,
            worker_name: Optional[str] = None,
            queue_name: Optional[str] = default_queue_name,
            cron_jobs: Optional[Sequence[CronJob]] = None,
            redis_settings: RedisSettings = None,
            redis_pool: AioRedis = None,
            burst: bool = False,
            on_startup: Optional['StartupShutdown'] = None,
            on_shutdown: Optional['StartupShutdown'] = None,
            handle_signals: bool = True,
            max_jobs: int = 10,
            job_timeout: 'SecondsTimedelta' = 300,
            keep_result: 'SecondsTimedelta' = 3600,
            keep_result_forever: bool = False,
            poll_delay: 'SecondsTimedelta' = 1,
            queue_read_limit: Optional[int] = None,
            max_tries: int = 5,
            health_check_interval: 'SecondsTimedelta' = 1,
            health_check_key: Optional[str] = None,
            ctx: Optional[Dict[Any, Any]] = None,
            retry_jobs: bool = True,
            allow_abort_jobs: bool = False,
            max_burst_jobs: int = -1,
            job_serializer: Optional[Serializer] = None,
            job_deserializer: Optional[Deserializer] = None,
    ):
        self.functions: Dict[str, Union[Function, CronJob]] = {f.name: f for f in map(func, functions)}

        if queue_name is None:
            if redis_pool is not None:
                queue_name = redis_pool.default_queue_name
            else:
                raise ValueError('If queue_name is absent, redis_pool must be present.')
        self.queue_name = queue_name
        self.worker_name = worker_name or self.name
        self.cron_jobs: List[CronJob] = []
        if cron_jobs is not None:
            assert all(isinstance(cj, CronJob) for cj in cron_jobs), 'cron_jobs, must be instances of CronJob'
            self.cron_jobs = list(cron_jobs)
            # 普通任务 + 定时任务
            self.functions.update({cj.name: cj for cj in self.cron_jobs})

        # 方法列表 > 0
        assert len(self.functions) > 0, 'at least one function or cron_job must be registered'
        self.burst = burst
        self.on_startup = on_startup
        self.on_shutdown = on_shutdown
        # 最大并发 sem
        self.sem = asyncio.BoundedSemaphore(max_jobs)
        self.job_timeout_s = to_seconds(job_timeout)
        self.keep_result_s = to_seconds(keep_result)
        self.keep_result_forever = keep_result_forever
        self.poll_delay_s = to_seconds(poll_delay)
        self.queue_read_limit = queue_read_limit or max(max_jobs * 5, 100)
        self._queue_read_offset = 0
        self.max_tries = max_tries
        self.health_check_interval = to_seconds(health_check_interval)

        # 指定健康检查 key
        if health_check_key is None:
            self.health_check_key = f'{health_check_key_suffix}{self.worker_name}'
        else:
            self.health_check_key = health_check_key
        # 指定 redis 连接池
        self._pool = redis_pool

        if self._pool is None:
            self.redis_settings: Optional[RedisSettings] = redis_settings or RedisSettings()
        else:
            self.redis_settings = None

        # self.tasks 保存运行当前正在运行的作业协同路由的引用
        self.tasks: Dict[str, asyncio.Task[Any]] = {}
        # self.job_tasks 保存实际运行的作业的引用
        self.job_tasks: Dict[str, asyncio.Task[Any]] = {}
        self.main_task: Optional[asyncio.Task[None]] = None
        self.loop = asyncio.get_event_loop()

        # 上下文管理 字典类型
        self.ctx = ctx or {}
        max_timeout = max(f.timeout_s or self.job_timeout_s for f in self.functions.values())
        # 运行的最大超时时间
        self.in_progress_timeout_s = (max_timeout or 0) + 10

        # 一堆默认状态
        self.jobs_complete = 0
        self.jobs_retried = 0
        self.jobs_failed = 0
        self.j_ongoing = 0
        self._last_health_check: float = 0
        self._last_health_check_log: Optional[str] = None

        # 信号
        self._handle_signals = handle_signals
        if self._handle_signals:
            self._add_signal_handler(signal.SIGINT, self.handle_sig)
            self._add_signal_handler(signal.SIGTERM, self.handle_sig)

        self.on_stop: Optional[Callable[[Signals], None]] = None

        # 是否在重试和取消时重试作业错误
        self.retry_jobs = retry_jobs
        self.allow_abort_jobs = allow_abort_jobs
        self.aborting_tasks: Set[str] = set()

        self.max_burst_jobs = max_burst_jobs
        self.job_serializer = job_serializer
        self.job_deserializer = job_deserializer

    @property
    def name(self):
        hostname = socket.gethostname()
        shortname, _, _ = hostname.partition('.')
        return f'{shortname}.{os.getpid()}'

    async def _set_worker_state(self, _pool, worker_name):
        w_ = JobWorker(
            queue_name=self.queue_name,
            worker_name=worker_name,
            functions=list(self.functions.keys()),
            enqueue_time=timestamp_ms(),
            is_action=True)
        worker_ = dataclasses.asdict(w_)
        await _pool.set(f'{worker_key}:{self.worker_name}', json.dumps(worker_))

    async def _set_functions_state(self, _pool):
        _ = []
        for func in self.functions.values():
            f_ = JobFunc(
                function_name=func.name,
                coroutine_name=func.coroutine.__qualname__,
                enqueue_time=timestamp_ms(),
                is_timer=isinstance(func, CronJob),
            )

            function_ = dataclasses.asdict(f_)
            _.append(function_)
        await _pool.set(f'{func_key}', json.dumps(_))

    def run(self) -> None:
        """
        同步函数来运行 worker
        最后关闭 worker 连接。
        同步函数里面写着 异步函数 用同步调用
        """
        self.main_task = self.loop.create_task(self.main())
        try:
            self.loop.run_until_complete(self.main_task)
        except asyncio.CancelledError:  # pragma: no cover
            # happens on shutdown, fine
            pass
        finally:
            self.loop.run_until_complete(self.close())

    async def async_run(self) -> None:
        """
        Asynchronously run the worker, does not close connections. Useful when testing.
        """
        self.main_task = self.loop.create_task(self.main())
        await self.main_task

    async def run_check(self, retry_jobs: Optional[bool] = None, max_burst_jobs: Optional[int] = None) -> int:
        """
        Run :func:`aiorq.worker.Worker.async_run`, check for failed jobs and raise :class:`aiorq.worker.FailedJobs`
        if any jobs have failed.
        :return: number of completed jobs
        """
        if retry_jobs is not None:
            self.retry_jobs = retry_jobs
        if max_burst_jobs is not None:
            self.max_burst_jobs = max_burst_jobs
        await self.async_run()
        if not self.jobs_failed:
            return self.jobs_complete
        failed_job_results = [r for r in await self.pool.all_job_results() if not r.success]
        raise FailedJobs(self.jobs_failed, failed_job_results)

    # 方法变属性而已
    @property
    def pool(self) -> AioRedis:
        return cast(AioRedis, self._pool)

    async def main(self) -> None:
        if self._pool is None:
            self._pool = await create_pool(
                self.redis_settings,
                job_deserializer=self.job_deserializer,
                job_serializer=self.job_serializer,
                default_queue_name=self.queue_name,
            )

        # 设置 redis 值
        await self._set_worker_state(_pool=self._pool, worker_name=self.worker_name)
        await self._set_functions_state(_pool=self._pool)

        # 输出一些队列信息
        logger.info(f'Aiorq Version: {__version__}')
        logger.info(f'Starting Queue: {self.queue_name}')
        logger.info(f'Starting Worker: {self.worker_name}')
        logger.info(f'Starting Functions: {", ".join(self.functions)}')
        await log_redis_info(self.pool, logger.info)

        # 将 redis 作为上下文环境
        self.ctx['redis'] = self.pool

        # 开始的钩子方法
        if self.on_startup:
            await self.on_startup(self.ctx)

        # 工作者开始循环
        async for _ in poll(self.poll_delay_s):  # noqa F841
            await self._poll_iteration(worker_name=self.worker_name)

            if self.burst:
                if 0 <= self.max_burst_jobs <= self._jobs_started():
                    await asyncio.gather(*self.tasks.values())
                    return None
                queued_jobs = await self.pool.zcard(self.queue_name)
                if queued_jobs == 0:
                    await asyncio.gather(*self.tasks.values())
                    return None

    # 开始执行任务列表
    async def _poll_iteration(self, worker_name) -> None:
        """
        从主队列排序集数据结构中获取挂起作业的ID,并启动这些作业,然后删除自我完成的任何任务。任务。
        """

        # 获取的最大并发队列任务数
        count = self.queue_read_limit
        if self.burst and self.max_burst_jobs >= 0:
            burst_jobs_remaining = self.max_burst_jobs - self._jobs_started()
            if burst_jobs_remaining < 1:
                return
            count = min(burst_jobs_remaining, count)

        async with self.sem:  # 在我们有空间运行作业之前,不要 zrangebyscore
            now = timestamp_ms()
            # 巧妙de用到了 zrangebyscore 属性，获取一组区间值，如果 执行时间（score）在此区间内才能取出任务job_ids
            # print(f"获取到最大区间：{now}  数量：{count}")
            job_ids = await self.pool.zrangebyscore(
                self.queue_name, min=float('-inf'), start=self._queue_read_offset, num=count, max=now)
            # print(f"获取到一组 jobs: {job_ids}")

        # 任务开始工作
        await self.start_jobs(job_ids, worker_name)

        # 如果允许中断
        if self.allow_abort_jobs:
            await self._cancel_aborted_jobs()

        # 收回已完成的任务并等待结果返回
        # t 是 asyncio task 可回调
        for job_id, t in list(self.tasks.items()):
            if t.done():
                del self.tasks[job_id]
                # 需要确保运行_作业中的错误得到传播
                t.result()
        # 定期健康检查
        await self.heart_beat()

    # 获取中止作业排序集中的作业ID, 然后取消这些任务。
    async def _cancel_aborted_jobs(self) -> None:
        """
        检查“中止作业”排序集中的作业ID,然后取消这些任务。
        """
        async with self.pool.pipeline(transaction=True) as pipe:
            pipe.zrange(abort_jobs_ss, start=0, end=-1)
            pipe.zremrangebyscore(abort_jobs_ss, min=timestamp_ms() + abort_job_max_age, max=float('inf'))
            abort_job_ids, _ = await pipe.execute()

        aborted: Set[str] = set()
        for job_id_bytes in abort_job_ids:
            job_id = job_id_bytes.decode()
            # 取出 abort_job_id 并且去 job_tasks 查询得到 task
            try:
                task = self.job_tasks[job_id]
            except KeyError:
                pass
            else:
                # 加入 aborted 集合并且取消 task
                aborted.add(job_id)
                task.cancel()

        if aborted:
            # 更新集合到 aborting_tasks
            self.aborting_tasks.update(aborted)
            #  Zrem 命令用于移除有序集中的一个或多个成员，不存在的成员将被忽略
            await self.pool.zrem(abort_jobs_ss, *aborted)

    # 开始执行普通任务
    async def start_jobs(self, job_ids: List[bytes], worke_namer: str) -> None:
        """
        对于每个作业id,获取作业定义,检查它是否未运行,并在任务中启动它
        """
        for job_id_b in job_ids:
            # 获取一个锁 这里为什么要这么设计呢
            await self.sem.acquire()
            # 产生正在运行的 in_progress_key_prefix
            job_id = job_id_b.decode()
            in_progress_key = in_progress_key_prefix + job_id
            async with self.pool.pipeline(transaction=True) as pipe:
                await pipe.unwatch()
                await pipe.watch(in_progress_key)
                ongoing_exists = await pipe.exists(in_progress_key)
                score = await pipe.zscore(self.queue_name, job_id)
                # print(f"任务将在 {score} 执行")
                if ongoing_exists or not score:
                    # 作业已在其他位置开始,或已完成并从队列中移除
                    # 否则直接跳过 (防止重复执行)
                    self.sem.release()
                    logger.debug('job %s already running elsewhere', job_id)
                    continue

                pipe.multi()
                # print("任务开始了!~ 改变状态为正在运行中 !!")
                pipe.psetex(in_progress_key, int(self.in_progress_timeout_s * 1000), b'1')
                try:
                    await pipe.execute()
                except (ResponseError, WatchError):
                    # job already started elsewhere since we got 'existing'
                    self.sem.release()
                    logger.debug('multi-exec error, job %s already started elsewhere', job_id)
                else:
                    # 调用创建 任务 并执行任务
                    # print("调用创建 任务 并执行任务!~")
                    t = self.loop.create_task(self.run_job(job_id, score, worke_namer))
                    # 回调方法 释放锁
                    t.add_done_callback(lambda _: self.sem.release())
                    self.tasks[job_id] = t

    # 运行任务
    async def run_job(self, job_id: str, score: int, worker_name: str) -> None:  # noqa: C901
        start_ms = timestamp_ms()
        async with self.pool.pipeline(transaction=True) as pipe:
            pipe.get(job_key_prefix + job_id)
            pipe.incr(retry_key_prefix + job_id)
            pipe.expire(retry_key_prefix + job_id, 88400)
            if self.allow_abort_jobs:
                pipe.zrem(abort_jobs_ss, job_id)
                v, job_try, _, abort_job = await pipe.execute()
            else:
                v, job_try, _ = await pipe.execute()
                abort_job = False

        function_name, enqueue_time_ms = '<unknown>', 0
        args: Tuple[Any, ...] = ()
        kwargs: Dict[Any, Any] = {}

        # 任务失败时
        async def job_failed(exc: BaseException) -> None:
            self.jobs_failed += 1
            result_data_ = serialize_result(
                function=function_name,
                args=args,
                kwargs=kwargs,
                job_try=job_try,
                enqueue_time_ms=enqueue_time_ms,
                success=False,
                result=exc,
                start_ms=start_ms,
                finished_ms=timestamp_ms(),
                ref=f'{job_id}:{function_name}',
                serializer=self.job_serializer,
                queue_name=self.queue_name,
                worker_name=worker_name
            )
            await asyncio.shield(self.finish_failed_job(job_id, result_data_))

        # 任务id 失效, 直接调用错误
        if not v:
            logger.warning('job %s expired', job_id)
            return await job_failed(JobExecutionFailed('job expired'))

        try:
            # 反序列化取出 function_name, args, kwargs, enqueue_job_try, enqueue_time_ms
            function_name, args, kwargs, enqueue_job_try, enqueue_time_ms = deserialize_job_raw(
                v, deserializer=self.job_deserializer
            )
        except SerializationError as e:
            logger.exception('deserializing job %s failed', job_id)
            return await job_failed(e)

        # 这里是判断该方法是否已经加入、存在于中止队列中,如果在 abort_job 为 True,直接抛出 asyncio.CancelledError
        # 因为如果调用了 abort 方法 会将其 job_id 加入到中止队列,所以这里要判断是否存在于 中止队列中
        if abort_job:
            t = (timestamp_ms() - enqueue_time_ms) / 1000
            logger.info('%6.2fs ⊘ %s:%s aborted before start', t, job_id, function_name)
            return await job_failed(asyncio.CancelledError())

        try:
            # 获取方法 类型为 Function, CronJob
            function: Union[Function, CronJob] = self.functions[function_name]
        except KeyError:
            # 不存在  预防方法 self.functions 为空列表的时候
            logger.warning('job %s, function %r not found', job_id, function_name)
            return await job_failed(JobExecutionFailed(f'function {function_name!r} not found'))

        # 包含属性 next_run 有就是定时任务
        if hasattr(function, 'next_run'):
            # 定时任务 需要 keep_in_progress (一直在进行中)
            ref = function_name
            keep_in_progress: Optional[float] = keep_cronjob_progress
        else:
            ref = f'{job_id}:{function_name}'
            keep_in_progress = None

        # 限定工作重试次数并产生 retry_key_prefix
        # enqueue_job_try: 任务重试次数
        # job_try: 已经重试了多少次
        if enqueue_job_try and enqueue_job_try > job_try:
            job_try = enqueue_job_try
            await self.pool.setex(retry_key_prefix + job_id, 88400, str(job_try))

        # 最大重试次数
        max_tries = self.max_tries if function.max_tries is None else function.max_tries

        # 工作重试次数大于方法重试次数 立即返回执行失败
        if job_try > max_tries:
            t = (timestamp_ms() - enqueue_time_ms) / 1000
            logger.warning('%6.2fs ! %s max retries %d exceeded', t, ref, max_tries)
            self.jobs_failed += 1
            result_data = serialize_result(
                function_name,
                args,
                kwargs,
                job_try,
                enqueue_time_ms,
                False,
                JobExecutionFailed(f'max {max_tries} retries exceeded'),
                start_ms,
                timestamp_ms(),
                ref,
                self.queue_name,
                worker_name,
                serializer=self.job_serializer,
            )
            return await asyncio.shield(self.finish_failed_job(job_id, result_data))
        result = no_result
        exc_extra = None
        finish = False
        timeout_s = self.job_timeout_s if function.timeout_s is None else function.timeout_s
        incr_score: Optional[int] = None
        # print("合并上下文 ctx !~")
        job_ctx = {
            'job_id': job_id,
            'job_try': job_try,
            'enqueue_time': ms_to_datetime(enqueue_time_ms),
            'score': score,
        }
        ctx = {**self.ctx, **job_ctx}
        start_ms = timestamp_ms()
        success = False
        try:
            s = args_to_string(args, kwargs)
            extra = f' job_try={job_try}' if job_try > 1 else ''
            # print(f"启动时间是: {start_ms} ")
            if (start_ms - score) > 1200:
                extra += f' delayed={(start_ms - score) / 1000:0.2f}s'
            logger.info('%6.2fs → %s(%s)%s', (start_ms - enqueue_time_ms) / 1000, ref, s, extra)
            self.job_tasks[job_id] = task = self.loop.create_task(function.coroutine(ctx, *args, **kwargs))

            # 如果超过预定的超时时间做 取消处理
            cancel_handler = self.loop.call_at(self.loop.time() + timeout_s, task.cancel)
            # run repr(result) and extra inside try/except as they can raise exceptions
            try:
                result = await task
            except (Exception, asyncio.CancelledError) as e:
                exc_extra = getattr(e, 'extra', None)
                if callable(exc_extra):
                    exc_extra = exc_extra()
                raise
            else:
                result_str = '' if result is None else truncate(repr(result))
            finally:
                del self.job_tasks[job_id]
                cancel_handler.cancel()

        except (Exception, asyncio.CancelledError) as e:
            finished_ms = timestamp_ms()
            t = (finished_ms - start_ms) / 1000

            if self.retry_jobs and isinstance(e, Retry):
                incr_score = e.defer_score
                logger.info('%6.2fs ↻ %s retrying job in %0.2fs', t, ref, (e.defer_score or 0) / 1000)
                if e.defer_score:
                    incr_score = e.defer_score + (timestamp_ms() - score)
            elif job_id in self.aborting_tasks and isinstance(e, asyncio.CancelledError):
                logger.info('%6.2fs ⊘ %s aborted', t, ref)
                result = e
                finish = True
                self.aborting_tasks.remove(job_id)
            elif self.retry_jobs and isinstance(e, (asyncio.CancelledError, RetryJob)):
                logger.info('%6.2fs ↻ %s cancelled, will be run again', t, ref)
            else:
                logger.exception(
                    '%6.2fs ! %s failed, %s: %s', t, ref, e.__class__.__name__, e, extra={'extra': exc_extra}
                )
                result = e
                finish = True
            self.jobs_failed += 1
        else:
            success, finish = True, True
            finished_ms = timestamp_ms()
            self.jobs_complete += 1
            logger.info('%6.2fs ← %s ● %s', (finished_ms - start_ms) / 1000, ref, result_str)

        async def complete_job():
            keep_result_forever = (
                self.keep_result_forever if function.keep_result_forever is None else function.keep_result_forever
            )
            result_timeout_s = self.keep_result_s if function.keep_result_s is None else function.keep_result_s
            result_data = None
            if result is not no_result and (keep_result_forever or result_timeout_s > 0):
                result_data = serialize_result(
                    function_name,
                    args,
                    kwargs,
                    job_try,
                    enqueue_time_ms,
                    success,
                    result,
                    start_ms,
                    finished_ms,
                    ref,
                    self.queue_name,
                    worker_name,
                    serializer=self.job_serializer,
                )

            await asyncio.shield(
                self.finish_complete_job(
                    job_id, finish, result_data, result_timeout_s, keep_result_forever, incr_score, keep_in_progress
                )
            )

        await complete_job()

    # 完成任务
    async def finish_complete_job(
            self,
            job_id: str,
            finish: bool,
            result_data: Optional[bytes],
            result_timeout_s: Optional[float],
            keep_result_forever: bool,
            incr_score: Optional[int],
            keep_in_progress: Optional[float],
    ) -> None:
        async with self.pool.pipeline(transaction=True) as pipe:
            await pipe.unwatch()
            pipe.multi()
            delete_keys = []
            in_progress_key = in_progress_key_prefix + job_id
            if keep_in_progress is None:
                delete_keys += [in_progress_key]
            else:
                pipe.expire(in_progress_key, to_ms(keep_in_progress))

            if finish:
                if result_data:
                    # print(result_data)
                    expire = None if keep_result_forever else result_timeout_s
                    pipe.set(result_key_prefix + job_id, result_data, px=to_ms(expire))
                delete_keys += [retry_key_prefix + job_id, job_key_prefix + job_id]
                pipe.zrem(abort_jobs_ss, job_id)
                pipe.zrem(self.queue_name, job_id)
            elif incr_score:
                pipe.zincrby(self.queue_name, incr_score, job_id)

            if delete_keys:
                pipe.delete(*delete_keys)
            await pipe.execute()

    # 失败完成工作任务
    async def finish_failed_job(self, job_id: str, result_data: Optional[bytes]) -> None:
        async with self.pool.pipeline(transaction=True) as pipe:
            await pipe.unwatch()
            pipe.multi()
            pipe.delete(
                retry_key_prefix + job_id,
                in_progress_key_prefix + job_id,
                job_key_prefix + job_id,
            )
            pipe.zrem(abort_jobs_ss, job_id)
            pipe.zrem(self.queue_name, job_id)
            # result_data would only be None if serializing the result fails
            keep_result = self.keep_result_forever or self.keep_result_s > 0
            if result_data is not None and keep_result:  # pragma: no branch
                expire = 0 if self.keep_result_forever else self.keep_result_s
                pipe.set(result_key_prefix + job_id, result_data, px=to_ms(expire))
            await pipe.execute()

    # 定时健康检查
    async def heart_beat(self) -> None:
        now = datetime.now()
        await self.record_health()
        cron_window_size = max(self.poll_delay_s, 0.5)  # Clamp the cron delay to 0.5
        await self.run_cron(now, cron_window_size)

    # 执行定时任务
    async def run_cron(self, n: datetime, delay: float, num_windows: int = 2) -> None:
        job_futures = set()

        cron_delay = timedelta(seconds=delay * num_windows)

        this_hb_cutoff = n + cron_delay

        for cron_job in self.cron_jobs:
            if cron_job.next_run is None:
                if cron_job.run_at_startup:
                    cron_job.next_run = n
                else:
                    cron_job.calculate_next(n)
                    # 在任何情况下,都不会运行此迭代。
                    continue

            # 如果下一次执行时间是在下一个时间段,我们将cron排队
            # delay * num_windows (by default 0.5 * 2 = 1 second).
            if cron_job.next_run < this_hb_cutoff:
                job_id = f'{cron_job.name}:{to_unix_ms(cron_job.next_run)}' if cron_job.unique else None
                job_futures.add(
                    self.pool.enqueue_job(
                        cron_job.name, **cron_job.kwargs, _job_id=job_id, _queue_name=self.queue_name, _defer_until=cron_job.next_run
                    )
                )
                cron_job.calculate_next(cron_job.next_run)

        job_futures and await asyncio.gather(*job_futures)

    # 健康检查详情
    async def record_health(self) -> None:
        now_ts = time()
        if (now_ts - self._last_health_check) < self.health_check_interval:
            # print("健康检查间隔时间", self.health_check_interval)
            return
        self._last_health_check = now_ts
        self.j_ongoing = sum(not t.done() for t in self.tasks.values())
        queued = await self.pool.zcard(self.queue_name)
        info = {
            "j_complete": self.jobs_complete,
            "j_failed": self.jobs_failed,
            "j_retried": self.jobs_retried,
            "j_ongoing": self.j_ongoing,
            "queued": queued
        }
        # print("健康检查:", info)
        await self.pool.psetex(self.health_check_key, int((self.health_check_interval + 1) * 1000), json.dumps(info))

    def _add_signal_handler(self, signum: Signals, handler: Callable[[Signals], None]) -> None:
        try:
            self.loop.add_signal_handler(signum, partial(handler, signum))
        except NotImplementedError:  # pragma: no cover
            logger.debug('Windows does not support adding a signal handler to an eventloop')

    def _jobs_started(self) -> int:
        return self.jobs_complete + self.jobs_retried + self.jobs_failed + len(self.tasks)

    def handle_sig(self, signum: Signals) -> None:
        sig = Signals(signum)
        logger.info(
            'shutdown on %s ◆ %d jobs complete ◆ %d failed ◆ %d retries ◆ %d ongoing to cancel',
            sig.name,
            self.jobs_complete,
            self.jobs_failed,
            self.jobs_retried,
            len(self.tasks),
        )
        for t in self.tasks.values():
            if not t.done():
                t.cancel()
        self.main_task and self.main_task.cancel()
        self.on_stop and self.on_stop(sig)

    async def close(self) -> None:
        if not self._handle_signals:
            self.handle_sig(signal.SIGUSR1)
        if not self._pool:
            return

        # redis 键设置为 删除或者延迟  默认一周
        w_ = JobWorker(
            is_action=False,
            queue_name=self.queue_name,
            worker_name=self.worker_name,
            functions=[],
            enqueue_time=timestamp_ms()
        )
        worker_ = dataclasses.asdict(w_)
        await self.pool.psetex(f'{worker_key}:{self.worker_name}',
                               int(worker_key_close_expire * 1000),
                               json.dumps(worker_))

        await asyncio.gather(*self.tasks.values())
        await self.pool.delete(self.health_check_key)

        if self.on_shutdown:
            await self.on_shutdown(self.ctx)

        await self.pool.close()
        self._pool = None

    def __repr__(self) -> str:
        return (
            f'<Worker j_complete={self.jobs_complete} j_failed={self.jobs_failed} j_retried={self.jobs_retried} '
            f'j_ongoing={self.j_ongoing}>'
        )


def get_kwargs(settings_cls: 'WorkerSettingsType') -> Dict[str, NameError]:
    worker_args = set(inspect.signature(Worker).parameters.keys())
    d = settings_cls if isinstance(settings_cls, dict) else settings_cls.__dict__
    return {k: v for k, v in d.items() if k in worker_args}


def create_worker(settings_cls: 'WorkerSettingsType', **kwargs: Any) -> Worker:
    return Worker(**{**get_kwargs(settings_cls), **kwargs})  # type: ignore


def run_worker(settings_cls: 'WorkerSettingsType', **kwargs: Any) -> Worker:
    worker = create_worker(settings_cls, **kwargs)
    worker.run()
    return worker


# 查询健康 key 是否存在
async def async_check_health(
        redis_settings: Optional[RedisSettings],
        health_check_key: Optional[str] = None,
        worker_name: Optional[str] = None,
) -> int:
    redis_settings = redis_settings or RedisSettings()
    redis: AioRedis = await create_pool(redis_settings)
    worker_name = worker_name or default_worker_name
    health_check_key = health_check_key or f'{health_check_key_suffix}{worker_name}'

    data = await redis.get(health_check_key)
    if not data:
        logger.warning('Health check failed: no health check sentinel value found')
        r = 1
    else:
        logger.info('Health check successful: %s', data)
        r = 0
    await redis.close()
    return r


# 验证健康 key 是否存在
def check_health(settings_cls: 'WorkerSettingsType') -> int:
    """
    Run a health check on the worker and return the appropriate exit code.
    :return: 0 if successful, 1 if not
    """
    cls_kwargs = get_kwargs(settings_cls)
    redis_settings = cast(Optional[RedisSettings], cls_kwargs.get('redis_settings'))
    health_check_key = cast(Optional[str], cls_kwargs.get('health_check_key'))
    queue_name = cast(Optional[str], cls_kwargs.get('queue_name'))
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(async_check_health(redis_settings, health_check_key, queue_name))

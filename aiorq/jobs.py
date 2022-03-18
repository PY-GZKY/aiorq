import asyncio
import json
import logging
import warnings
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from aioredis import Redis

from constants import abort_jobs_ss, default_queue_name, in_progress_key_prefix, job_key_prefix, result_key_prefix
from utils import ms_to_datetime, poll, timestamp_ms

logger = logging.getLogger('aiorq.jobs')

Serializer = Callable[[Dict[str, Any]], bytes]
Deserializer = Callable[[bytes], Dict[str, Any]]


class JobStatus(str, Enum):
    """
    Enum of job statuses.
    """
    #: job is in the queue, time it should be run not yet reached
    deferred = 'deferred'
    #: job is in the queue, time it should run has been reached
    queued = 'queued'
    #: job is in progress
    in_progress = 'in_progress'
    #: job is complete, result is available
    complete = 'complete'
    #: job not found in any way
    not_found = 'not_found'


@dataclass
class JobWorker:
    worker_name: str
    queue_name: str
    functions: list
    enqueue_time: datetime
    is_action: bool


@dataclass
class JobFunc:
    function_name: str
    coroutine_name: str
    enqueue_time: datetime
    is_timer: bool


@dataclass
class JobDef:
    function: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    job_try: int
    enqueue_time: datetime
    score: Optional[int]

    def __post_init__(self) -> None:
        if isinstance(self.score, float):
            self.score = int(self.score)


@dataclass
class JobResult(JobDef):
    success: bool
    result: Any
    start_time: datetime
    finish_time: datetime
    queue_name: str
    worker_name: str
    job_id: Optional[str] = None

    def __post_init__(self) -> None:
        ...


class Job:
    """
    Holds data a reference to a job.
    """

    __slots__ = 'job_id', '_redis', '_queue_name', '_deserializer'

    def __init__(
            self,
            job_id: str,
            redis: Redis,
            _queue_name: str = default_queue_name,
            _worker_name: str = None,
            _deserializer: Optional[Deserializer] = None,
    ):
        self.job_id = job_id
        self._redis = redis
        self._queue_name = _queue_name
        self._deserializer = _deserializer

    async def result(
            self, timeout: Optional[float] = None, *, poll_delay: float = 0.5, pole_delay: float = None
    ) -> Any:
        """
        获取作业的结果，包括在尚未可用时等待。如果工作引发了一个例外，它将在这里提出。
        :param timeout:在引发“TimeoutError”之前等待作业结果的最长时间将永远等待
        :param poll_delay:为作业结果轮询redis的频率
        :param pole_delay:已弃用，请改用poll_delay
        这里一直等待任务完成并返回结果
        否则一直阻塞
        """
        if pole_delay is not None:
            warnings.warn(
                '"pole_delay" is deprecated, use the correct spelling "poll_delay" instead', DeprecationWarning
            )
            poll_delay = pole_delay

        async for delay in poll(poll_delay):
            info = await self.result_info()
            if info:
                result = info.result
                # print("info: ",info)
                if info.success:
                    return result
                elif isinstance(result, (Exception, asyncio.CancelledError)):
                    raise result
                else:
                    raise SerializationError(result)
            if timeout is not None and delay > timeout:
                raise asyncio.TimeoutError()

    async def info(self) -> Optional[JobDef]:
        """
        作业的所有信息，包括其结果（如果可用），都不会等待结果
        这里如果获取不到 result info 就会去获取 job info
        """
        info: Optional[JobDef] = await self.result_info()
        # 这里如果获取不到就会去获取 job info
        if not info:
            v = await self._redis.get(job_key_prefix + self.job_id)
            if v:
                info = deserialize_job(v, deserializer=self._deserializer)
        if info:
            # 获取到了就把 score 值附上去并返回
            info.score = await self._redis.zscore(self._queue_name, self.job_id)
        return info

    async def result_info(self) -> Optional[JobResult]:
        """
        有关作业结果的信息（如果可用）不会等待结果。不会引发异常 即使这份工作养了一只。
        这里会立即返回结果  如果还没有结果 那就返回 None
        """
        v = await self._redis.get(result_key_prefix + self.job_id)
        return deserialize_result(v, deserializer=self._deserializer) if v else None

    async def status(self) -> JobStatus:
        """
        工作的状态方法
        """
        # 如果 result_key_prefix 键存在 说明可以返回结果 complete
        if await self._redis.exists(result_key_prefix + self.job_id):
            return JobStatus.complete
        # 如果 in_progress_key_prefix 键存在 说明正在进行中 in_progress
        elif await self._redis.exists(in_progress_key_prefix + self.job_id):
            return JobStatus.in_progress
        else:
            # 任务不见了
            score = await self._redis.zscore(self._queue_name, self.job_id)
            if not score:
                return JobStatus.not_found
            # 任务超时 或者 还没有被执行
            return JobStatus.deferred if score > timestamp_ms() else JobStatus.queued

    async def abort(self, *, timeout: Optional[float] = None, poll_delay: float = 0.5) -> bool:
        """
        工作终止
        :param timeout:在引发“TimeoutError”之前等待作业结果的最长时间，不会永远等待任何人
        :param poll_delay:为作业结果轮询redis的频率
        :return:如果作业正确中止，则为True，否则为False
        """
        # 设置终止键
        await self._redis.zadd(abort_jobs_ss, {self.job_id: timestamp_ms()})
        try:
            # 尝试获取结果
            await self.result(timeout=timeout, poll_delay=poll_delay)
        # 如果抛出取消的异常 则终止成功  否则终止失败
        except asyncio.CancelledError:
            return True
        else:
            return False

    def __repr__(self) -> str:
        return f'<aiorq job {self.job_id}>'


class SerializationError(RuntimeError):
    pass


class DeserializationError(SerializationError):
    pass


def serialize_job(
        function_name: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        job_try: Optional[int],
        enqueue_time_ms: int,
        queue_name: str,
        *,
        serializer: Optional[Serializer] = None,
) -> Optional[str]:
    data = {
        'job_try': job_try,
        'function': function_name,
        'args': args,
        'kwargs': kwargs,
        'enqueue_time': enqueue_time_ms,
        'queue_name': queue_name
    }
    if serializer is None:
        serializer = json.dumps
    try:
        return serializer(data)
    except Exception as e:
        raise SerializationError(f'unable to serialize job "{function_name}"') from e


def deserialize_job(r: bytes, *, deserializer: Optional[Deserializer] = None) -> JobDef:
    if deserializer is None:
        deserializer = json.loads
    try:
        d = deserializer(r)
        return JobDef(
            function=d['function'],
            args=d['args'],
            kwargs=d['kwargs'],
            job_try=d['job_try'],
            enqueue_time=ms_to_datetime(d['enqueue_time']),
            score=None,
        )
    except Exception as e:
        raise DeserializationError('unable to deserialize job') from e


def deserialize_job_raw(
        r: bytes,
        *,
        deserializer: Optional[Deserializer] = None
) -> Tuple[str, Tuple[Any, ...], Dict[str, Any], int, int]:
    if deserializer is None:
        deserializer = json.loads
    try:
        d = deserializer(r)
        return d['function'], d['args'], d['kwargs'], d['job_try'], d['enqueue_time']
    except Exception as e:
        raise DeserializationError('unable to deserialize job') from e


def serialize_result(
        function: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        job_try: int,
        enqueue_time_ms: int,
        success: bool,
        result: Any,
        start_ms: int,
        finished_ms: int,
        ref: str,
        queue_name: str,
        worker_name: str,
        *,
        serializer: Optional[Serializer] = None,
) -> Optional[str]:
    data = {
        'job_try': job_try,
        'function': function,
        'args': args,
        'kwargs': kwargs,
        'enqueue_time_ms': enqueue_time_ms,
        'success': success,
        'result': result,
        'start_ms': start_ms,
        'finished_ms': finished_ms,
        'queue_name': queue_name,
        'worker_name': worker_name
    }
    if serializer is None:
        serializer = json.dumps
    try:
        return serializer(data)
    except Exception:
        logger.warning('error serializing result of %s', ref, exc_info=True)

    # use string in case serialization fails again
    data.update(r='unable to serialize result', s=False)
    try:
        return serializer(data)
    except Exception:
        logger.critical('error serializing result of %s even after replacing result', ref, exc_info=True)
    return None


def deserialize_result(r: bytes, *, deserializer: Optional[Deserializer] = None) -> JobResult:
    if deserializer is None:
        deserializer = json.loads
    try:
        d = deserializer(r)
        return JobResult(
            job_try=d['job_try'],
            function=d['function'],
            args=d['args'],
            kwargs=d['kwargs'],
            enqueue_time=ms_to_datetime(d['enqueue_time_ms']),
            score=None,
            success=d['success'],
            result=d['result'],
            start_time=ms_to_datetime(d['start_ms']),
            finish_time=ms_to_datetime(d['finished_ms']),
            queue_name=d.get('queue_name', '<unknown>'),
            worker_name=d.get('worker_name', '<unknown>')
        )
    except Exception as e:
        raise DeserializationError('unable to deserialize job result') from e


def deserialize_func(
        r: bytes,
        *,
        deserializer: Optional[Deserializer] = None
):
    if deserializer is None:
        deserializer = json.loads
    try:
        d = deserializer(r)
        return [
            JobFunc(
                function_name=dd["function_name"],
                coroutine_name=dd["coroutine_name"],
                is_timer=dd["is_timer"],
                enqueue_time=ms_to_datetime(dd['enqueue_time']))
            for dd in d
        ]
    except Exception as e:
        raise DeserializationError('unable to deserialize job func') from e


def deserialize_worker(
        r: bytes,
        *,
        deserializer: Optional[Deserializer] = None
):
    if deserializer is None:
        deserializer = json.loads
    try:
        d = deserializer(r)
        return JobWorker(
            worker_name=d["worker_name"],
            queue_name=d["queue_name"],
            functions=d["functions"],
            enqueue_time=ms_to_datetime(d['enqueue_time']),
            is_action=d["is_action"]
        )
    except Exception as e:
        raise DeserializationError('unable to deserialize job worker') from e

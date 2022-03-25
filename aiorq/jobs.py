import asyncio
import logging
import warnings
from typing import Any, Optional

from aioredis import Redis

from constants import abort_jobs_ss, default_queue_name, in_progress_key_prefix, job_key_prefix, result_key_prefix
from exception import SerializationError
from serialize import Deserializer, deserialize_job, deserialize_result
from specs import JobStatus, JobDef, JobResult
from utils import poll, timestamp_ms

logger = logging.getLogger('aiorq.jobs')


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
        # print("self.job_id:", self.job_id)
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

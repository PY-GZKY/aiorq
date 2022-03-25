import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from exception import SerializationError, DeserializationError
from specs import JobWorker, JobFunc, JobDef, JobResult
from utils import ms_to_datetime

logger = logging.getLogger('aiorq.serialize')

Serializer = Callable[[Dict[str, Any]], bytes]
Deserializer = Callable[[bytes], Dict[str, Any]]


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
            state=None,
            job_id=None,
            start_time=None,
            queue_name=None,
            worker_name=None,
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
        job_id: str,
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
        'worker_name': worker_name,
        'job_id':job_id
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
            worker_name=d.get('worker_name', '<unknown>'),
            job_id=d.get('job_id'),
            state=d.get('state')
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

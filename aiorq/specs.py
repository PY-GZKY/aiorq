from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple


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
    health_check: Dict[str, Any] = None


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
    state: Optional[str]
    job_id: Optional[str]
    start_time: Optional[datetime]
    queue_name: Optional[str]
    worker_name: Optional[str]


    def __post_init__(self) -> None:
        if isinstance(self.score, float):
            self.score = int(self.score)


@dataclass
class JobResult(JobDef):
    success: bool
    result: Any
    finish_time: datetime

    def __post_init__(self) -> None:
        ...

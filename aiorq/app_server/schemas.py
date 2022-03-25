from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from pydantic import BaseModel

class HealthCheckModel(BaseModel):
    j_complete: int
    j_failed: int
    j_retried: int
    j_ongoing: int
    queued: int


class FunctionModel(BaseModel):
    function_name: str
    coroutine_name: str
    is_timer: bool
    enqueue_time: datetime


class WorkerModel(BaseModel):
    queue_name: str
    worker_name: str
    functions: list
    is_action: bool
    enqueue_time: datetime
    health_check: Dict[str, Any]

class WorkerListModel(BaseModel):
    workers: List[WorkerModel]


class IndecModel(BaseModel):
    functions: List[FunctionModel]
    workers: List[WorkerModel]



class JobDefModel(BaseModel):
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

class JobDefsModel(BaseModel):
    rows: List[JobDefModel]


class JobResult_(BaseModel):
    function: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    job_try: int
    enqueue_time: datetime
    score: Optional[int]
    success: bool
    result: Any
    start_time: datetime
    finish_time: datetime
    queue_name: str
    worker_name: str
    job_id: Optional[str] = None

class JobResultModel(BaseModel):
    rows: List[JobResult_]
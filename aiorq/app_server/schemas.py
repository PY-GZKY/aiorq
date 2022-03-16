from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from pydantic import BaseModel


class FunctionModel(BaseModel):
    name: str
    coroutine: str
    is_timer: bool
    time_: datetime


class WorkerModel(BaseModel):
    queue_name: str
    worker_name: str
    is_action: bool
    time_: datetime  # Optional[Union[float, datetime.timedelta]]


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
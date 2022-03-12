from fastapi import APIRouter

from aiorq.fastapi_server_.api.api_v1.index import router as index_router
from aiorq.fastapi_server_.api.api_v1.job import router as job_router
from aiorq.fastapi_server_.api.api_v1.result import router as result_router
from aiorq.fastapi_server_.api.api_v1.task import router as task_router
from aiorq.fastapi_server_.api.api_v1.worker import router as worker_router

router = APIRouter()

router.include_router(index_router, tags=["Index"])
router.include_router(job_router, prefix="/job", tags=["Job"])
router.include_router(task_router, prefix="/task", tags=["Task"])
router.include_router(worker_router, prefix="/worker", tags=["Worker"])
router.include_router(result_router, prefix="/result", tags=["Result"])

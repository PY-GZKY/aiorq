from fastapi import APIRouter

from aiorq.app_server.v1.index import router as index_router
from aiorq.app_server.v1.job import router as job_router
from aiorq.app_server.v1.setting import router as setting_router

api_v1_router = APIRouter()

api_v1_router.include_router(index_router, tags=["统计信息"])
api_v1_router.include_router(job_router, prefix="/job", tags=["Job"])
api_v1_router.include_router(setting_router, prefix="/redis_info", tags=["redis_info"])
# api_v1_router.include_router(task_router, prefix="/func", tags=["Func"])
# api_v1_router.include_router(worker_router, prefix="/worker", tags=["Worker"])

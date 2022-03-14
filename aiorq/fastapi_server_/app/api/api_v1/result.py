from fastapi import APIRouter
from starlette.requests import Request

router = APIRouter()


@router.get("/get_all_result")
async def get_all_result(request: Request, worker=None, task=None, job_id=None):
    all_result_ = await request.app.state.redis.all_job_results()
    if worker:
        all_result_ = [result_ for result_ in all_result_ if result_.get("worker_name") == worker]
    if task:
        all_result_ = [result_ for result_ in all_result_ if result_.get("function") == task]
    if job_id:
        all_result_ = [result_ for result_ in all_result_ if result_.get("job_id") == job_id]

    return {"results_": all_result_}


@router.delete("")
async def delete_result():
    ...

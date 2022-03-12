from fastapi import APIRouter, Depends
from starlette.requests import Request

from rearq import CronTask, ReArq
from rearq.server import templates
from rearq.server.depends import get_rearq
from rearq.server.models import JobResult
from rearq.utils import ms_to_datetime

router = APIRouter()


@router.get("", include_in_schema=False)
async def get_tasks(request: Request, rearq: ReArq = Depends(get_rearq)):
    task_map = rearq.task_map
    tasks = []
    cron_tasks = []
    for task_name, task in task_map.items():
        item = {
            "name": task_name,
            "queue": task.queue,
        }
        job_result = await JobResult.filter(job__task=task_name).order_by("-id").first()
        if job_result:
            item["last_time"] = job_result.finish_time
        else:
            item["last_time"] = None
        if isinstance(task, CronTask):
            item["cron"] = task.cron
            task.set_next()
            item["next_time"] = ms_to_datetime(task.next_run)
            cron_tasks.append(item)
        else:
            tasks.append(item)
    return templates.TemplateResponse(
        "task.html",
        {"request": request, "page_title": "task", "tasks": tasks, "cron_tasks": cron_tasks},
    )

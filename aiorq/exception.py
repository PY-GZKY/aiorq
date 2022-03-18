from typing import TYPE_CHECKING, Any, List, Optional

from jobs import JobResult
from utils import to_ms

if TYPE_CHECKING:
    from typing_ import SecondsTimedelta, StartupShutdown, WorkerCoroutine, WorkerSettingsType  # noqa F401


class Retry(RuntimeError):
    """
    重试作业的特殊异常（如果尚未达到最大重试次数）。
    :param defer:重新运行作业之前等待的持续时间
    """

    def __init__(self, defer: Optional['SecondsTimedelta'] = None):
        self.defer_score: Optional[int] = to_ms(defer)

    def __repr__(self) -> str:
        return f'<Retry defer {(self.defer_score or 0) / 1000:0.2f}s>'

    def __str__(self) -> str:
        return repr(self)


class JobExecutionFailed(RuntimeError):
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, JobExecutionFailed):
            return self.args == other.args
        return False


class FailedJobs(RuntimeError):
    def __init__(self, count: int, job_results: List[JobResult]):
        self.count = count
        self.job_results = job_results

    def __str__(self) -> str:
        if self.count == 1 and self.job_results:
            exc = self.job_results[0].result
            return f'1 job failed {exc!r}'
        else:
            return f'{self.count} jobs failed:\n' + '\n'.join(repr(r.result) for r in self.job_results)

    def __repr__(self) -> str:
        return f'<{str(self)}>'


class RetryJob(RuntimeError):
    pass

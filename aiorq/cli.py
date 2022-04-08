import asyncio
import logging.config
import os
import sys
from signal import Signals
from typing import TYPE_CHECKING, cast

import click
import uvicorn
from pydantic.utils import import_string

from .app_server.main_ import app
from .logs import default_log_config
from .version import __version__
from .worker import check_health, create_worker, run_worker

if TYPE_CHECKING:
    from .typing_ import WorkerSettingsType

burst_help = 'Batch mode: exit once no jobs are found in any queue.'
health_check_help = 'Health Check: run a health check and exit.'
watch_help = 'Watch a directory and reload the worker upon changes.'
verbose_help = 'Enable verbose output.'

@click.group()
@click.version_option(__version__, '-V', '--version')
def cli() -> None:
    """
    Job queues in python with asyncio and redis.
    CLI to run the aiorq worker.
    """


@cli.command(help="Start a worker.")
@click.argument('worker-settings', type=str, required=True)
@click.option('--burst/--no-burst', default=None, help=burst_help)
@click.option('--check', is_flag=True, help=health_check_help)
@click.option('--watch', type=click.Path(exists=True, dir_okay=True, file_okay=False), help=watch_help)
@click.option('-v', '--verbose', is_flag=True, help=verbose_help)
@click.pass_context
def worker(*, worker_settings: str, burst: bool, check: bool, watch: str, verbose: bool):
    """
    Job queues in python with asyncio and redis.
    CLI to run the aiorq worker.
    """
    sys.path.append(os.getcwd())

    worker_settings_ = cast('WorkerSettingsType', import_string(worker_settings))  # <class 'tasks.WorkerSettings'>
    logging.config.dictConfig(default_log_config(verbose))

    if check:
        exit(check_health(worker_settings_))
    elif watch:
        asyncio.get_event_loop().run_until_complete(watch_reload(watch, worker_settings_))
    else:
        kwargs = {} if burst is None else {'burst': burst}
        run_worker(worker_settings_, **kwargs)


@cli.command(help="Start a server.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Listen host.")
@click.option("--port", default=8080, show_default=True, help="Listen port.")
@click.pass_context
def server(host: str, port: int):
    uvicorn.run(app=app, host=host, port=port, debug=True)


async def watch_reload(path: str, worker_settings: 'WorkerSettingsType') -> None:
    try:
        from watchgod import awatch
    except ImportError as e:  # pragma: no cover
        raise ImportError('watchgod not installed, use `pip install watchgod`') from e

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def worker_on_stop(s: Signals) -> None:
        if s != Signals.SIGUSR1:  # pragma: no cover
            stop_event.set()

    worker = create_worker(worker_settings)
    try:
        worker.on_stop = worker_on_stop
        loop.create_task(worker.async_run())
        async for _ in awatch(path, stop_event=stop_event):
            print('\nfiles changed, reloading aiorq worker...')
            worker.handle_sig(Signals.SIGUSR1)
            await worker.close()
            loop.create_task(worker.async_run())
    finally:
        await worker.close()


if __name__ == '__main__':
    cli()

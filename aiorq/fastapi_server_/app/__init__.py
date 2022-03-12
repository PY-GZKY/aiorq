# -*- coding: utf-8 -*-
import os
import sys
import time

from app.db.mongo_db import db
from app.db.redis_db import RedisCore
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_profiler.profiler_middleware import PyInstrumentProfilerMiddleware
from fastapi_utils.tasks import repeat_every
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from aiorq.fastapi_server_.logger import logger

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI

from aiorq.fastapi_server_.config import settings
from aiorq.fastapi_server_.api import router as api_v1_router


def create_app():
    app = FastAPI(
        debug=settings.DEBUG,
        title=settings.PROJECT_NAME,  # 项目名称
        description=settings.DESCRIPTION,  # 项目简介
        # docs_url=None,  redoc_url=None
        # docs_url=f"{settings.API_V1_STR}/docs",  # 自定义 docs文档的访问路径
        # openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # 中间件
    register_middleware(app)

    # 注册redis
    register_redis(app)

    # 注册mongodb
    register_mongodb(app)

    # 跨域设置
    register_cors(app)

    # 注册路由
    register_router(app)

    # 尝试一个定时任务
    # register_task(app)

    # 静态文件
    # register_static_file(app)

    return app


def register_middleware(app: FastAPI):
    if settings.PROFILER_ON:
        app.add_middleware(PyInstrumentProfilerMiddleware, server_app=app, )
        # app.add_middleware(CProfileMiddleware, enable=True, server_app = app, filename='./output.pstats', strip_dirs = False, sort_by='cumulative')


def register_task(app: FastAPI):
    # 尝试写一个定时任务
    @app.on_event("startup")
    @repeat_every(seconds=10)  # 1 hour
    async def con_task() -> None:
        logger.debug(f'你好 定时任务启动 {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}!')


def register_redis(app: FastAPI):
    @app.on_event("startup")
    async def startup():
        redis = await RedisCore().get_redis_pool()
        # 先挂上 fast 对象
        app.state.redis = redis

        # 初始化缓存 FastAPICache
        FastAPICache.init(RedisBackend(redis), prefix=settings.REDIS_CACHE_KEY)
        logger.debug("REDIS 数据库初始化成功 ... DONE")

    @app.on_event('shutdown')
    async def shutdown():
        app.state.redis.close()
        await app.state.redis.wait_closed()


def register_mongodb(app: FastAPI):
    @app.on_event("startup")
    async def connect_to_mongo():
        try:
            db.client = AsyncIOMotorClient(settings.MONGODB_URL,
                                           # maxPoolSize=settings.MAX_CONNECTIONS_COUNT,
                                           # minPoolSize=settings.MIN_CONNECTIONS_COUNT
                                           )
            logger.debug("MONGODB 数据库初始化成功 ... DONE")
        except:
            logger.error("MONGODB 数据库初始化失败 ... DONE")

    @app.on_event("shutdown")
    async def close_mongo_connection():
        logger.debug("MONGODB 数据库连接关闭 ... DONE")


def register_cors(app: FastAPI):
    """
    支持跨域
    :param app:
    :return:
    """
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def register_router(app: FastAPI):
    """
    :param app:
    :return:
    """
    app.include_router(
        api_v1_router,
        # prefix=settings.API_V1_STR  # 前缀
    )


# todo vue 静态文件
def register_static_file(app: FastAPI) -> None:
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="./static"), name="static")

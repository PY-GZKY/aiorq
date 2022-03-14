# -*- coding: utf-8 -*-
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from aiorq import create_pool
from aiorq.connections import RedisSettings
from aiorq.fastapi_server_.app.config import settings
from aiorq.fastapi_server_.app.db.mongodb_ import db
from aiorq.fastapi_server_.app.logger import logger

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI

from aiorq.fastapi_server_.app.api import router as api_v1_router


def create_app():
    app = FastAPI(
        debug=settings.DEBUG,
        title=settings.PROJECT_NAME,
        description=settings.DESCRIPTION,
        # docs_url=f"{settings.API_V1_STR}/docs",
        # openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    register_redis(app)
    # register_mongodb(app)
    register_cors(app)
    # register_router(app)
    # register_static_file(app)

    return app


def register_redis(app: FastAPI):
    @app.on_event("startup")
    async def startup():
        app.state.redis = await create_pool(
            RedisSettings(
                host=os.getenv("REDIS_HOST", "127.0.0.1"),
                port=os.getenv("REDIS_PORT", 6379),
                database=os.getenv("REDIS_DATABASE", 0),
                password=os.getenv("REDIS_PASSWORD", None)
            )
        )

    @app.on_event('shutdown')
    async def shutdown():
        await app.state.redis.close()


def register_mongodb(app: FastAPI):
    @app.on_event("startup")
    async def connect_to_mongo():
        try:
            db.client = AsyncIOMotorClient(settings.MONGODB_URL,
                                           maxPoolSize=settings.MAX_CONNECTIONS_COUNT,
                                           minPoolSize=settings.MIN_CONNECTIONS_COUNT
                                           )
            logger.debug("MONGODB 数据库初始化成功 ... DONE")
        except:
            logger.error("MONGODB 数据库初始化失败 ... DONE")

    @app.on_event("shutdown")
    async def close_mongo_connection():
        logger.debug("MONGODB 数据库连接关闭 ... DONE")


def register_cors(app: FastAPI):
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def register_router(app: FastAPI):
    app.include_router(
        api_v1_router,
        # prefix=settings.API_V1_STR  # 前缀
    )


def register_static_file(app: FastAPI) -> None:
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="./static"), name="static")

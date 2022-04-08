# -*- coding: utf-8 -*-
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from aiorq.connections import RedisSettings, create_pool
from .v1 import api_v1_router
from .config import settings
from .db.mongodb_ import mongodb_
from .logger import logger



def create_app():
    app = FastAPI(
        debug=settings.DEBUG,
        title=settings.PROJECT_NAME,
        description=settings.DESCRIPTION,
        # docs_url=f"{settings.API_V1_STR}/docs",
        # openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # register_redis(app)
    # register_mongodb(app_server)
    register_cors(app)
    register_router(app)
    # register_static_file(app_server)

    return app


def register_redis(app: FastAPI):
    @app.on_event("startup")
    async def startup():
        app.state.redis = await create_pool(
            RedisSettings(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                database=settings.REDIS_DATABASE,
                password=settings.REDIS_PASSWORD,
            )
        )

    @app.on_event('shutdown')
    async def shutdown():
        await app.state.redis.close()


def register_mongodb(app: FastAPI):
    @app.on_event("startup")
    async def connect_to_mongo():
        try:
            mongodb_.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
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
        api_v1_router
    )


def register_static_file(app: FastAPI) -> None:
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="./static"), name="static")

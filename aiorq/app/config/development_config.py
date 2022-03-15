#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
from typing import List, Union
from urllib import parse

from pydantic import AnyHttpUrl, BaseSettings, validator


class Settings(BaseSettings):
    DEBUG: bool = True
    PROFILER_ON: bool = 0
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "(-ASp+_)-Ulhw0848hnvVG-iqKyJSD&*&^-H3C9mqEqSl8KN-YRzRE"

    # token 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 100

    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 项目信息
    PROJECT_NAME: str = "Aiorq"
    DESCRIPTION: str = "Aiorq Server"
    SERVER_NAME: str = "API_V1"
    SERVER_HOST: AnyHttpUrl = "http://127.0.0.1:8080"

    # 跨域
    BACKEND_CORS_ORIGINS: List[str] = ['*']

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # 缓存 key
    REDIS_CACHE_KEY = "fastapi_cache:"
    HOST_DETAIL_KEY = "host_detail:"
    HOST_CACHE_EXPIRE = 60 * 60 * 24 * 7

    # Redis
    REDIS_USERNAME: str = os.getenv("REDIS_USERNAME", None)
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "sanmaoyou_admin_")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "192.168.0.141")
    REDIS_PORT: int = os.getenv("REDIS_PORT", 6379)
    REDIS_DATABASE: int = os.getenv("REDIS_DATABASE", 15)
    REDIS_ENCODING: str = os.getenv("REDIS_ENCODING", "utf8")
    REDIS_MAX_CONNECTIONS: int = os.getenv("REDIS_MAX_CONNECTIONS", 10)
    REDIS_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}"

    # MongoDB
    MAX_CONNECTIONS_COUNT = int(os.getenv("MAX_CONNECTIONS_COUNT", 10))
    MIN_CONNECTIONS_COUNT = int(os.getenv("MIN_CONNECTIONS_COUNT", 1))
    MONGODB_URL = os.getenv("MONGODB_URL", "")
    if not MONGODB_URL:
        MONGO_HOST: str = os.getenv("MONGO_HOST", "127.0.0.1")
        MONGO_PORT: int = os.getenv("MONGO_PORT", 27017)
        MONGO_USER: str = os.getenv("MONGO_USER", "admin")
        MONGO_PASS: str = os.getenv("MONGO_PASS", "")
        MONGO_DB: str = os.getenv("MONGO_DB", "")
        MONGO_TABLE: str = os.getenv("MONGO_TABLE", "")
        MONGODB_URL: str = f"mongodb://{MONGO_USER}:{parse.quote_plus(MONGO_PASS)}@{MONGO_HOST}:{MONGO_PORT}"

    class Config:
        case_sensitive = True


settings = Settings()

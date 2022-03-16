# -*- coding: utf-8 -*
# @Time : 2020/12/22 17:29

from motor.motor_asyncio import AsyncIOMotorClient


class MotorClient:
    client: AsyncIOMotorClient = None


mongodb_ = MotorClient()
async def get_async_motor() -> AsyncIOMotorClient:
    return mongodb_.client

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from starlette.status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT


router = APIRouter()



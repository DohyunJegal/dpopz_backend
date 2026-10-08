"""실행: uvicorn main:app --reload

리버스 프록시(nginx) 뒤에서는 실제 클라이언트 IP 를 쓰도록 --proxy-headers 옵션 사용
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import account, admin, api, reports, votes
from app.db import connect, init_db


@asynccontextmanager
async def lifespan(_):
    conn = connect()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="DPOPz", lifespan=lifespan)
app.include_router(api.router)
app.include_router(account.router)
app.include_router(votes.router)
app.include_router(reports.router)
app.include_router(admin.router)

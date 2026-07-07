"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import mp_rewrite, xhs_note

api_router = APIRouter(prefix="/api/v1", tags=["v1"])

# 小红书爆款笔记项目
api_router.include_router(xhs_note.router, prefix="/xhs", tags=["xhs"])

# 公众号文章改写项目
api_router.include_router(mp_rewrite.router, prefix="/mp", tags=["mp"])


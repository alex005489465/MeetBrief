import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from .database import init_db
from .routers import meetings
from .modules.transcription import coordinator_loop

# 初始化資料庫
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # 啟動時：開始協調器背景任務
    coordinator_task = asyncio.create_task(coordinator_loop())
    print("協調器背景任務已啟動")

    yield

    # 關閉時：取消協調器任務
    coordinator_task.cancel()
    try:
        await coordinator_task
    except asyncio.CancelledError:
        pass
    print("協調器背景任務已停止")


# 建立 FastAPI 應用
app = FastAPI(
    title="MeetBrief",
    description="會議語音轉文字摘要工具",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(meetings.router)

# 靜態檔案
frontend_path = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


@app.get("/")
async def root():
    """首頁"""
    return FileResponse(str(frontend_path / "index.html"))


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy", "service": "MeetBrief"}

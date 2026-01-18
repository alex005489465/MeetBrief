import os
import sys
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

# 加入 shared 模組路徑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ..database import get_db
from ..models import Meeting
from ..config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE
from ..utils.audio import get_audio_duration, is_valid_audio_format, get_safe_filename
from shared.queue import enqueue_task, get_task_status, enqueue_diarize_task
from backend.modules.transcription import get_coordinator


def fix_filename_encoding(filename: str) -> str:
    """
    修正檔名編碼問題（Windows curl 可能用錯誤編碼傳送中文檔名）

    Args:
        filename: 原始檔名

    Returns:
        修正後的檔名
    """
    if not filename:
        return filename

    # 嘗試不同的編碼組合來修正
    encodings_to_try = [
        ('latin-1', 'utf-8'),      # 常見的錯誤：UTF-8 被當作 Latin-1
        ('cp1252', 'utf-8'),       # Windows 西歐編碼
        ('latin-1', 'cp950'),      # Big5/CP950 (繁體中文)
        ('latin-1', 'gbk'),        # GBK (簡體中文)
    ]

    for decode_enc, encode_enc in encodings_to_try:
        try:
            # 嘗試將字串轉換回原始位元組，然後用正確編碼解讀
            fixed = filename.encode(decode_enc).decode(encode_enc)
            # 檢查是否看起來像正常的文字（沒有亂碼特徵）
            if not any(ord(c) > 0xFFFF for c in fixed):
                return fixed
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue

    # 如果都失敗，返回原始檔名
    return filename

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class TranscriptUpdate(BaseModel):
    """轉錄文字更新模型"""
    transcript: str


class TitleUpdate(BaseModel):
    """標題更新模型"""
    title: str


class TranscribeOptions(BaseModel):
    """轉錄選項模型"""
    mode: str = "transcribe_and_summarize"  # transcribe_only, transcribe_and_summarize
    diarization: bool = False
    num_speakers: int = None  # 說話者數量（None 為自動偵測）


@router.post("/upload")
async def upload_meeting(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上傳會議音檔

    Args:
        file: 上傳的音檔
        db: 資料庫 session

    Returns:
        會議記錄
    """
    # 修正檔名編碼
    original_filename = fix_filename_encoding(file.filename)

    # 檢查檔案格式
    if not is_valid_audio_format(original_filename, ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案格式。支援的格式: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 讀取檔案內容
    content = await file.read()

    # 檢查檔案大小
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"檔案過大。最大允許大小: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB"
        )

    # 生成唯一檔名
    safe_filename = get_safe_filename(original_filename)
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"
    filepath = UPLOADS_DIR / unique_filename

    # 儲存檔案
    with open(filepath, "wb") as f:
        f.write(content)

    # 取得音檔長度
    duration = get_audio_duration(str(filepath))

    # 建立會議記錄
    title = Path(original_filename).stem
    meeting = Meeting(
        title=title,
        filename=original_filename,
        filepath=str(filepath),
        duration=duration,
        status="pending"
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # 發送任務到佇列
    enqueue_task("transcribe", meeting.id)

    # 通知協調器追蹤此任務（預設：轉錄+摘要，無說話者分離）
    coordinator = get_coordinator()
    coordinator.add_task(meeting.id, "transcribe_and_summarize", False)

    return meeting.to_dict()


@router.get("")
async def list_meetings(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    取得會議列表
    """
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).offset(skip).limit(limit).all()
    return [m.to_dict() for m in meetings]


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    """
    取得單一會議詳情
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")
    return meeting.to_dict()


@router.get("/{meeting_id}/status")
async def get_meeting_status(meeting_id: int, db: Session = Depends(get_db)):
    """
    取得會議處理狀態（包含 Redis 佇列狀態）
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    # 取得佇列狀態
    queue_status = get_task_status(meeting_id)

    return {
        "id": meeting_id,
        "status": meeting.status,
        "queue_status": queue_status
    }


@router.delete("/{meeting_id}")
async def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    """
    刪除會議記錄
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    # 刪除音檔
    if meeting.filepath and os.path.exists(meeting.filepath):
        os.remove(meeting.filepath)

    # 刪除資料庫記錄
    db.delete(meeting)
    db.commit()

    return {"message": "會議記錄已刪除"}


@router.post("/{meeting_id}/transcribe")
async def transcribe_meeting(
    meeting_id: int,
    options: TranscribeOptions = None,
    db: Session = Depends(get_db)
):
    """
    手動觸發轉錄

    Args:
        meeting_id: 會議 ID
        options: 轉錄選項（mode: transcribe_only/transcribe_and_summarize, diarization: bool）
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    if meeting.status in ["transcribing", "summarizing"]:
        raise HTTPException(status_code=400, detail="會議正在處理中")

    # 解析選項
    if options is None:
        options = TranscribeOptions()

    # 重置狀態
    meeting.status = "pending"
    meeting.transcript = None
    meeting.summary = None
    meeting.error_message = None
    db.commit()

    # 發送轉錄任務到 whisper worker
    enqueue_task(
        "transcribe",
        meeting.id,
        mode=options.mode,
        diarization=options.diarization,
        num_speakers=options.num_speakers
    )

    # 如果需要說話者分離，同時發送到 diarizer worker
    if options.diarization:
        enqueue_diarize_task(
            meeting.id,
            meeting.filepath,
            num_speakers=options.num_speakers
        )

    # 通知協調器追蹤此任務
    coordinator = get_coordinator()
    coordinator.add_task(meeting.id, options.mode, options.diarization)

    return {
        "message": "已加入處理佇列",
        "mode": options.mode,
        "diarization": options.diarization,
        "num_speakers": options.num_speakers
    }


@router.post("/{meeting_id}/summarize")
async def summarize_meeting(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    手動觸發摘要生成
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="尚無轉錄文字，請先執行轉錄")

    if meeting.status == "summarizing":
        raise HTTPException(status_code=400, detail="正在生成摘要中")

    # 更新狀態
    meeting.status = "summarizing"
    db.commit()

    # 在背景執行摘要生成
    coordinator = get_coordinator()
    background_tasks.add_task(
        run_summarize_task,
        meeting_id,
        meeting.transcript
    )

    return {"message": "已開始生成摘要"}


@router.put("/{meeting_id}/transcript")
async def update_transcript(
    meeting_id: int,
    data: TranscriptUpdate,
    db: Session = Depends(get_db)
):
    """
    編輯轉錄文字
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    meeting.transcript = data.transcript
    db.commit()
    return meeting.to_dict()


@router.put("/{meeting_id}/title")
async def update_title(
    meeting_id: int,
    data: TitleUpdate,
    db: Session = Depends(get_db)
):
    """
    更新會議標題
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    meeting.title = data.title
    db.commit()
    return meeting.to_dict()


@router.get("/{meeting_id}/export")
async def export_meeting(
    meeting_id: int,
    format: str = "markdown",
    db: Session = Depends(get_db)
):
    """
    匯出會議記錄
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="找不到會議記錄")

    if format == "markdown":
        content = generate_markdown_export(meeting)
        filename = f"{meeting.title}.md"
        media_type = "text/markdown"
    else:
        content = generate_txt_export(meeting)
        filename = f"{meeting.title}.txt"
        media_type = "text/plain"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


def generate_markdown_export(meeting: Meeting) -> str:
    """生成 Markdown 格式匯出"""
    lines = [
        f"# {meeting.title}",
        "",
        f"**檔案名稱**: {meeting.filename}",
        f"**音檔長度**: {format_duration(meeting.duration)}",
        f"**語言**: {meeting.language or '未偵測'}",
        f"**建立時間**: {meeting.created_at.strftime('%Y-%m-%d %H:%M:%S') if meeting.created_at else ''}",
        "",
        "---",
        "",
    ]

    if meeting.summary:
        lines.extend([
            "# 會議摘要",
            "",
            meeting.summary,
            "",
            "---",
            "",
        ])

    if meeting.transcript:
        lines.extend([
            "# 逐字稿",
            "",
            "```",
            meeting.transcript,
            "```",
        ])

    return "\n".join(lines)


def generate_txt_export(meeting: Meeting) -> str:
    """生成純文字格式匯出"""
    lines = [
        f"標題: {meeting.title}",
        f"檔案名稱: {meeting.filename}",
        f"音檔長度: {format_duration(meeting.duration)}",
        f"語言: {meeting.language or '未偵測'}",
        f"建立時間: {meeting.created_at.strftime('%Y-%m-%d %H:%M:%S') if meeting.created_at else ''}",
        "",
        "=" * 50,
        "",
    ]

    if meeting.summary:
        lines.extend([
            "【會議摘要】",
            "",
            meeting.summary,
            "",
            "=" * 50,
            "",
        ])

    if meeting.transcript:
        lines.extend([
            "【逐字稿】",
            "",
            meeting.transcript,
        ])

    return "\n".join(lines)


def format_duration(seconds: Optional[float]) -> str:
    """格式化時間長度"""
    if not seconds:
        return "未知"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}小時 {minutes}分 {secs}秒"
    elif minutes > 0:
        return f"{minutes}分 {secs}秒"
    else:
        return f"{secs}秒"


def run_summarize_task(meeting_id: int, transcript: str):
    """
    執行摘要生成任務（在背景執行）
    """
    from backend.database import SessionLocal
    from backend.models import Meeting
    from backend.modules.analysis import create_full_pipeline

    print(f"[Summarize] 開始處理會議 {meeting_id} 的摘要...")

    try:
        # 從帶時間戳的轉錄中提取純文字
        plain_text = extract_plain_text(transcript)

        # 執行分析管線
        pipeline = create_full_pipeline()
        results = pipeline.run(plain_text, [])

        # 取得摘要內容
        summary_result = results.get("summary", {})
        summary = summary_result.get("content", "")

        if not summary:
            raise ValueError("摘要生成失敗：無內容")

        # 更新資料庫
        db = SessionLocal()
        try:
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting.summary = summary
                meeting.status = "completed"
                meeting.error_message = None
                db.commit()
                print(f"[Summarize] 會議 {meeting_id} 摘要生成完成")
        finally:
            db.close()

    except Exception as e:
        print(f"[Summarize] 會議 {meeting_id} 摘要生成失敗: {e}")
        import traceback
        traceback.print_exc()

        # 更新錯誤狀態
        db = SessionLocal()
        try:
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting.status = "completed"
                meeting.error_message = f"摘要生成失敗: {str(e)}"
                db.commit()
        finally:
            db.close()


def extract_plain_text(transcript: str) -> str:
    """從帶時間戳的轉錄中提取純文字"""
    lines = transcript.split("\n")
    plain_parts = []
    for line in lines:
        if "]" in line:
            # 處理 [時間] [說話者] 文字 或 [時間] 文字
            parts = line.split("]")
            text = parts[-1].strip() if parts else ""
            if text:
                plain_parts.append(text)
    return "\n".join(plain_parts)

from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from .database import Base


class Meeting(Base):
    """會議記錄模型"""
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    duration = Column(Float, nullable=True)
    status = Column(String(50), default="pending")
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    language = Column(String(10), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """轉換為字典"""
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "duration": self.duration,
            "status": self.status,
            "transcript": self.transcript,
            "summary": self.summary,
            "language": self.language,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

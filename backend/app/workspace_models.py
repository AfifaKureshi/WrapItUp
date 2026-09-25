from sqlalchemy import ForeignKey, String, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .models import uid, now
from .database import Base
from sqlalchemy import DateTime
from datetime import datetime


class WorkspaceRecord(Base):
    """Versioned user-owned supplier, evidence and feedback records."""
    __tablename__ = 'workspace_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'), nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    attachment: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

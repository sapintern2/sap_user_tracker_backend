from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    total_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    daily_users = relationship("DailyUser", back_populates="upload", cascade="all, delete-orphan")
    deleted_as_previous = relationship(
        "DeletedUser",
        back_populates="previous_upload",
        foreign_keys="DeletedUser.previous_upload_id",
    )
    deleted_as_current = relationship(
        "DeletedUser",
        back_populates="current_upload",
        foreign_keys="DeletedUser.current_upload_id",
    )
    movements_as_previous = relationship(
        "ClassificationMovement",
        back_populates="previous_upload",
        foreign_keys="ClassificationMovement.previous_upload_id",
    )
    movements_as_current = relationship(
        "ClassificationMovement",
        back_populates="current_upload",
        foreign_keys="ClassificationMovement.current_upload_id",
    )

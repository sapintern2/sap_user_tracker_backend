from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class NewUser(Base):
    __tablename__ = "new_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    added_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    previous_upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), nullable=False)
    current_upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    previous_upload = relationship(
        "Upload",
        back_populates="new_users_as_previous",
        foreign_keys=[previous_upload_id],
    )
    current_upload = relationship(
        "Upload",
        back_populates="new_users_as_current",
        foreign_keys=[current_upload_id],
    )

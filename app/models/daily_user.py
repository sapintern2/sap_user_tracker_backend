from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DailyUser(Base):
    __tablename__ = "daily_users"
    __table_args__ = (
        UniqueConstraint("upload_id", "username", name="uq_daily_users_upload_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    upload = relationship("Upload", back_populates="daily_users")

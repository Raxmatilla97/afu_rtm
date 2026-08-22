from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base, TimestampMixin


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hemis_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped["Department | None"] = relationship(
        "Department", remote_side="Department.id", back_populates="children"
    )
    children: Mapped[list["Department"]] = relationship(
        "Department", back_populates="parent"
    )

    def __repr__(self) -> str:
        return f"<Department id={self.id} hemis_id={self.hemis_id} name={self.name!r}>"

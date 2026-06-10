from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class RowStateEnum(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"


class RowState(SQLModel, table=True):
    __tablename__ = "row_state"
    __table_args__ = (UniqueConstraint("element_repetition_id", "row_id"),)

    id: int | None = Field(default=None, primary_key=True)
    element_repetition_id: int = Field(foreign_key="element_repetition.id", index=True)
    row_id: int = Field(foreign_key="row.id")
    state: RowStateEnum = Field(default=RowStateEnum.not_started)
    stitch_position: int | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

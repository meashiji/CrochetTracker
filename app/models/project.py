from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Project(SQLModel, table=True):
    __tablename__ = "project"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Element(SQLModel, table=True):
    __tablename__ = "element"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str | None = None
    pattern_text: str | None = None
    repeat_count: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ElementRepetition(SQLModel, table=True):
    __tablename__ = "element_repetition"
    __table_args__ = (UniqueConstraint("element_id", "repetition_number"),)

    id: int | None = Field(default=None, primary_key=True)
    element_id: int = Field(foreign_key="element.id", index=True)
    repetition_number: int

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Row(SQLModel, table=True):
    __tablename__ = "row"
    __table_args__ = (UniqueConstraint("element_id", "position"),)

    id: int | None = Field(default=None, primary_key=True)
    element_id: int = Field(foreign_key="element.id", index=True)
    position: int
    content: str

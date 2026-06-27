"""project_name_varchar50

Revision ID: 479f6a3b988b
Revises: 1354362dad07
Create Date: 2026-06-27 11:50:08.297598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '479f6a3b988b'
down_revision: Union[str, Sequence[str], None] = '1354362dad07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # USING LEFT(name, 50) silently truncates any dev rows that exceed the new limit
    op.execute("ALTER TABLE project ALTER COLUMN name TYPE VARCHAR(50) USING LEFT(name, 50)")


def downgrade() -> None:
    op.alter_column("project", "name", type_=sa.Text(), existing_type=sa.String(50))

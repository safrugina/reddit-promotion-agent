"""add problem and differentiator fact types

Revision ID: 602bf5976e9e
Revises: 2338c140554a
Create Date: 2026-08-17 22:42:16.456774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '602bf5976e9e'
down_revision: Union[str, None] = '2338c140554a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE fact_type ADD VALUE IF NOT EXISTS 'problem'")
    op.execute("ALTER TYPE fact_type ADD VALUE IF NOT EXISTS 'differentiator'")


def downgrade() -> None:
    # Postgres does not support removing enum values; downgrade is a no-op.
    pass

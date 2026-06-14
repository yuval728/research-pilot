"""sanitize_paper_metadata

Revision ID: 006
Revises: 005
Create Date: 2026-06-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE papers
        SET metadata = NULL
        WHERE metadata IS NOT NULL
          AND jsonb_typeof(metadata) <> 'object'
        """
    )


def downgrade() -> None:
    pass

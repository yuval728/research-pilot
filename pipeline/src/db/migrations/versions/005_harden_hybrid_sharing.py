"""harden_hybrid_sharing

Revision ID: 005
Revises: 004
Create Date: 2026-05-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "papers", sa.Column("imported_from_paper_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_papers_imported_from_paper_id",
        "papers",
        "papers",
        ["imported_from_paper_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_papers_is_public", "papers", ["is_public"], unique=False)
    op.create_index("ix_papers_published_at", "papers", ["published_at"], unique=False)

    # One user can import a specific source paper only once.
    op.create_index(
        "uq_papers_user_import_source",
        "papers",
        ["user_id", "imported_from_paper_id"],
        unique=True,
        postgresql_where=sa.text("imported_from_paper_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_papers_user_import_source", table_name="papers")
    op.drop_index("ix_papers_published_at", table_name="papers")
    op.drop_index("ix_papers_is_public", table_name="papers")
    op.drop_constraint("fk_papers_imported_from_paper_id", "papers", type_="foreignkey")
    op.drop_column("papers", "imported_from_paper_id")

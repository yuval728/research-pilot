"""upgrade_embedding_dim

Revision ID: 002
Revises: 001
Create Date: 2024-04-22 22:32:00.000000

"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop existing index (required before altering dimension)
    op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_ivfflat")

    # 2. Alter column type
    # WARNING: This will fail if you have existing data.
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(1536)")

    # 3. Recreate index for the new dimension
    op.execute(
        "CREATE INDEX ix_embeddings_embedding_ivfflat ON embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_ivfflat")
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(768)")
    op.execute(
        "CREATE INDEX ix_embeddings_embedding_ivfflat ON embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )

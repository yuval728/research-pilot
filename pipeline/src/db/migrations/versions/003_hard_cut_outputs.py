"""hard_cut_outputs

Revision ID: 003
Revises: 002
Create Date: 2026-05-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Promote legacy `codegen` rows to strict output types.
    # Heuristic: explicit notebook paths become `code_notebook`, everything else `code_python`.
    op.execute(
        """
        UPDATE outputs
        SET output_type = CASE
            WHEN storage_path ILIKE '%.ipynb' THEN 'code_notebook'
            ELSE 'code_python'
        END
        WHERE output_type = 'codegen';
        """
    )

    # Basic path normalization for promoted inline placeholders.
    op.execute(
        """
        UPDATE outputs
        SET storage_path = regexp_replace(storage_path, '^inline:', '')
        WHERE output_type IN ('code_python', 'code_notebook')
          AND storage_path LIKE 'inline:%';
        """
    )

    # Post-migration validation: no legacy rows are allowed after hard cut.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM outputs WHERE output_type = 'codegen') THEN
                RAISE EXCEPTION 'Legacy codegen rows still present after migration';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Strict output rows collapse back to legacy codegen for rollback.
    op.execute(
        """
        UPDATE outputs
        SET output_type = 'codegen'
        WHERE output_type IN ('code_python', 'code_notebook');
        """
    )

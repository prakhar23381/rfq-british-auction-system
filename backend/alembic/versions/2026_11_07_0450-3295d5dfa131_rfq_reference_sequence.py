"""rfq reference sequence

Sequence behind generated reference IDs (RFQ-YYYY-NNNN). It is OWNED BY the reference_id
column so it is dropped with the table and reset by TRUNCATE ... RESTART IDENTITY.

Revision ID: 3295d5dfa131
Revises: 6040b72f1192
Create Date: 2026-11-07 04:50:34.894961

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3295d5dfa131"
down_revision: str | Sequence[str] | None = "6040b72f1192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE rfq_reference_seq START 1 OWNED BY rfqs.reference_id")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS rfq_reference_seq")

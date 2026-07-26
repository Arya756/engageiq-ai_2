"""add quiet hours and sensitivity to users

Revision ID: f25392335386
Revises: 07d3ea7f887d
Create Date: 2026-07-26 13:53:57.290850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f25392335386'
down_revision: Union[str, None] = '07d3ea7f887d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only add the 3 NEW columns for Issue #23 (Nudge Preferences).
    # Other columns (auth_provider, notification_enabled, etc.) already
    # exist in the database and were added by a previous migration.
    op.add_column('users', sa.Column('quiet_hours_start', sa.String(), nullable=True))
    op.add_column('users', sa.Column('quiet_hours_end', sa.String(), nullable=True))
    op.add_column(
        'users',
        sa.Column('sensitivity', sa.String(), nullable=False, server_default='normal'),
    )


def downgrade() -> None:
    # Undo the 3 columns we added above
    op.drop_column('users', 'sensitivity')
    op.drop_column('users', 'quiet_hours_end')
    op.drop_column('users', 'quiet_hours_start')

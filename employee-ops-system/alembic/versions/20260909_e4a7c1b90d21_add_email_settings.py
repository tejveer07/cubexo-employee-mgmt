"""add_email_settings

Revision ID: e4a7c1b90d21
Revises: 3562f6476b50
Create Date: 2026-09-09 00:00:00.000000

Adds outbound-email (SMTP) config columns to the org_settings singleton, used by
the project-assignment notification feature. See app/services/notifications.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a7c1b90d21'
down_revision: Union[str, None] = '3562f6476b50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('org_settings', sa.Column('smtp_host', sa.String(), nullable=True))
    op.add_column('org_settings', sa.Column('smtp_port', sa.Integer(), nullable=True))
    op.add_column('org_settings', sa.Column('smtp_username', sa.String(), nullable=True))
    op.add_column('org_settings', sa.Column('smtp_password', sa.String(), nullable=True))
    op.add_column('org_settings', sa.Column('smtp_use_tls', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('org_settings', sa.Column('smtp_use_ssl', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('org_settings', sa.Column('email_from', sa.String(), nullable=True))
    op.add_column('org_settings', sa.Column('email_from_name', sa.String(), nullable=True))
    op.add_column('org_settings', sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('org_settings', 'email_enabled')
    op.drop_column('org_settings', 'email_from_name')
    op.drop_column('org_settings', 'email_from')
    op.drop_column('org_settings', 'smtp_use_ssl')
    op.drop_column('org_settings', 'smtp_use_tls')
    op.drop_column('org_settings', 'smtp_password')
    op.drop_column('org_settings', 'smtp_username')
    op.drop_column('org_settings', 'smtp_port')
    op.drop_column('org_settings', 'smtp_host')

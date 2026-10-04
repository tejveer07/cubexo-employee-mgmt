"""add_cost_analysis_fields

Revision ID: bbc08225b914
Revises: 9414c3fbcf54
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbc08225b914'
down_revision: Union[str, None] = '9414c3fbcf54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('monthly_salary', sa.Numeric(12, 2), nullable=True))
    op.add_column('projects', sa.Column('monthly_income', sa.Numeric(12, 2), nullable=True))
    op.create_table('org_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('monthly_overhead', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO org_settings (id, monthly_overhead) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table('org_settings')
    op.drop_column('projects', 'monthly_income')
    op.drop_column('employees', 'monthly_salary')

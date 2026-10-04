"""salary_income_gst_history

Revision ID: 3562f6476b50
Revises: bbc08225b914
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3562f6476b50'
down_revision: Union[str, None] = 'bbc08225b914'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('employees', 'monthly_salary')
    op.drop_column('projects', 'monthly_income')

    op.add_column('projects', sa.Column('tds_rate', sa.Numeric(5, 2), nullable=True))
    op.add_column('projects', sa.Column('gst_applicable', sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table('salary_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('monthly_salary', sa.Numeric(12, 2), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'effective_from'),
    )
    op.create_index(op.f('ix_salary_history_id'), 'salary_history', ['id'], unique=False)

    op.create_table('project_income_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monthly_income', sa.Numeric(12, 2), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'effective_from'),
    )
    op.create_index(op.f('ix_project_income_history_id'), 'project_income_history', ['id'], unique=False)

    op.create_table('gst_rate_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gst_rate', sa.Numeric(5, 2), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('effective_from'),
    )
    op.create_index(op.f('ix_gst_rate_history_id'), 'gst_rate_history', ['id'], unique=False)

    # Anchor row: covers every existing/future project by default (18%) from an
    # intentionally early date, until an admin records a more specific change.
    op.execute("INSERT INTO gst_rate_history (gst_rate, effective_from) VALUES (18, '2000-01-01')")


def downgrade() -> None:
    op.drop_index(op.f('ix_gst_rate_history_id'), table_name='gst_rate_history')
    op.drop_table('gst_rate_history')
    op.drop_index(op.f('ix_project_income_history_id'), table_name='project_income_history')
    op.drop_table('project_income_history')
    op.drop_index(op.f('ix_salary_history_id'), table_name='salary_history')
    op.drop_table('salary_history')

    op.drop_column('projects', 'gst_applicable')
    op.drop_column('projects', 'tds_rate')

    op.add_column('projects', sa.Column('monthly_income', sa.Numeric(12, 2), nullable=True))
    op.add_column('employees', sa.Column('monthly_salary', sa.Numeric(12, 2), nullable=True))

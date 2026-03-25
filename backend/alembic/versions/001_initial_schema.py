"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create repositories table
    op.create_table(
        'repositories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('github_url', sa.String(), nullable=False),
        sa.Column('repo_name', sa.String(), nullable=False),
        sa.Column('repo_owner', sa.String(), nullable=False),
        sa.Column('primary_language', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_scanned_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_repositories_github_url', 'repositories', ['github_url'], unique=True)

    # Create scans table
    op.create_table(
        'scans',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('repository_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=True),

        # Core metrics
        sa.Column('total_cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('debt_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_hours', sa.Float(), server_default='0'),
        sa.Column('total_sprints', sa.Float(), server_default='0'),

        # Category breakdown
        sa.Column('cost_by_category', postgresql.JSONB(), nullable=True),

        # Rate info
        sa.Column('hourly_rate', sa.Float(), nullable=True),
        sa.Column('rate_confidence', sa.String(), nullable=True),

        # Repo profile snapshot
        sa.Column('team_size', sa.Integer(), nullable=True),
        sa.Column('bus_factor', sa.Integer(), nullable=True),
        sa.Column('repo_age_days', sa.Integer(), nullable=True),
        sa.Column('combined_multiplier', sa.Float(), nullable=True),
        sa.Column('primary_language', sa.String(), nullable=True),
        sa.Column('frameworks', postgresql.JSONB(), nullable=True),

        # LLM outputs
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('priority_actions', postgresql.JSONB(), nullable=True),
        sa.Column('roi_analysis', postgresql.JSONB(), nullable=True),

        # Full raw result
        sa.Column('raw_result', postgresql.JSONB(), nullable=True),

        # Metadata
        sa.Column('status', sa.String(), server_default='complete'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('scan_duration_seconds', sa.Float(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
    )
    op.create_index('ix_scans_repository_id', 'scans', ['repository_id'])
    op.create_index('ix_scans_job_id', 'scans', ['job_id'], unique=True)
    op.create_index('ix_scans_created_at', 'scans', ['created_at'])
    op.create_index('ix_scans_repo_created', 'scans', ['repository_id', 'created_at'])

    # Create debt_items table
    op.create_table(
        'debt_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scan_id', sa.String(), nullable=False),

        # Item details
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('function_name', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('severity', sa.String(), nullable=True),

        # Metrics
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('hours', sa.Float(), nullable=True),
        sa.Column('complexity', sa.Integer(), nullable=True),
        sa.Column('churn_multiplier', sa.Float(), nullable=True),

        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_debt_items_scan_id', 'debt_items', ['scan_id'])
    op.create_index('ix_debt_items_file_path', 'debt_items', ['file_path'])
    op.create_index('ix_debt_items_category', 'debt_items', ['category'])


def downgrade() -> None:
    op.drop_table('debt_items')
    op.drop_table('scans')
    op.drop_table('repositories')

"""Workspace records for supplier quotations, evidence files and feedback."""
from alembic import op
import sqlalchemy as sa
revision = 'b27e_workspace_records'
down_revision = '4d4c377019cb'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('workspace_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('attachment', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    for col in ('owner_id', 'kind', 'project_id'):
        op.create_index('ix_workspace_records_' + col, 'workspace_records', [col])

def downgrade():
    op.drop_table('workspace_records')

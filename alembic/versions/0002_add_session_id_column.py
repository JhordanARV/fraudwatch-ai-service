"""
Revision ID: 0002_add_session_id_column
Revises: 0001_create_tables
Create Date: 2025-05-10 22:54:45.000000
"""
revision = '0002_add_session_id_column'
down_revision = '0001_create_tables'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('analisis', sa.Column('session_id', sa.String(), nullable=True))

def downgrade():
    op.drop_column('analisis', 'session_id')

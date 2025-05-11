"""
Revision ID: 0003_add_origen_to_analisis
Revises: 0002_add_origen_to_analisis
Create Date: 2025-05-11 00:20:30

"""
revision = '0003_add_origen_to_analisis'
down_revision = '0002_add_session_id_column'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('analisis', sa.Column('origen', sa.String(), nullable=True))

def downgrade():
    op.drop_column('analisis', 'origen')

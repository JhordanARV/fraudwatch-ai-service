"""
Revision ID: 0001_create_tables
Revises: 
Create Date: 2025-05-10 22:50:00.000000
"""
revision = '0001_create_tables'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'usuarios',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('username', sa.String, unique=True, index=True, nullable=False),
        sa.Column('email', sa.String, unique=True, index=True, nullable=False),
        sa.Column('hashed_password', sa.String, nullable=False),
        sa.Column('fecha_registro', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'analisis',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('usuario_id', sa.Integer, sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('texto_analizado', sa.Text, nullable=False),
        sa.Column('resultado', sa.Text, nullable=False),
        sa.Column('fecha', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table('analisis')
    op.drop_table('usuarios')

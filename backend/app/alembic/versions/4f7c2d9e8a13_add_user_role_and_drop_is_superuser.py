"""Add user role and drop is_superuser

Revision ID: 4f7c2d9e8a13
Revises: fe56fa70289e
Create Date: 2026-11-18 17:24:27.344794

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '4f7c2d9e8a13'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    # Role values are literals on purpose: a migration is a frozen snapshot and
    # must not change when the application's Role enum does.

    # The server default gives every existing row, and every later insert that
    # does not set a role, the lowest privilege.
    op.add_column(
        'user',
        sa.Column('role', sa.String(length=32), server_default='member', nullable=False),
    )
    op.execute("UPDATE \"user\" SET role = 'admin' WHERE is_superuser")
    op.create_check_constraint(
        'ck_user_role', 'user', "role IN ('admin', 'manager', 'member')"
    )
    op.drop_column('user', 'is_superuser')


def downgrade():
    # Lossy but safe: is_superuser cannot express the manager role, so managers
    # become regular users. Nobody gains privilege on downgrade.
    op.add_column(
        'user',
        sa.Column('is_superuser', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("UPDATE \"user\" SET is_superuser = true WHERE role = 'admin'")
    op.drop_constraint('ck_user_role', 'user', type_='check')
    op.drop_column('user', 'role')

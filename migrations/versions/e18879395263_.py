"""Create GlobalState table

Revision ID: e18879395263
Revises: 
Create Date: 2023-02-28 17:20:32.512886

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e18879395263'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('GlobalState',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_account', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('GlobalState')
    # ### end Alembic commands ###

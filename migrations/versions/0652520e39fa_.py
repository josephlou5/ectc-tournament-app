"""Update EmailsSent table

Revision ID: 0652520e39fa
Revises: 32b526e449c1
Create Date: 2023-04-04 16:09:57.359078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0652520e39fa'
down_revision = '32b526e449c1'
branch_labels = None
depends_on = None


# There was no data in this table before this commit, so it's okay to
# add and remove non-nullable columns without any default values.


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('EmailsSent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('match_number', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('subject', sa.String(), nullable=False))
        batch_op.add_column(sa.Column('recipients', sa.String(), nullable=False))
        batch_op.add_column(sa.Column('template_name', sa.String(), nullable=False))
        batch_op.drop_column('matches')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('EmailsSent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('matches', sa.VARCHAR(), autoincrement=False, nullable=False))
        batch_op.drop_column('template_name')
        batch_op.drop_column('recipients')
        batch_op.drop_column('subject')
        batch_op.drop_column('match_number')

    # ### end Alembic commands ###

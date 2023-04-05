"""Add other recipient settings (coaches and spectators) to GlobalState

Revision ID: 02a758ab31db
Revises: 0652520e39fa
Create Date: 2023-04-05 15:04:30.374438

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '02a758ab31db'
down_revision = '0652520e39fa'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('GlobalState', schema=None) as batch_op:
        batch_op.add_column(sa.Column('send_to_coaches', sa.Boolean(), nullable=False, server_default="false"))
        batch_op.add_column(sa.Column('send_to_spectators', sa.Boolean(), nullable=False, server_default="false"))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('GlobalState', schema=None) as batch_op:
        batch_op.drop_column('send_to_spectators')
        batch_op.drop_column('send_to_coaches')

    # ### end Alembic commands ###

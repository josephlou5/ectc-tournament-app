"""Rename last roster spreadsheet to TMS spreadsheet

Revision ID: 6927bd10e170
Revises: c45d23518e0d
Create Date: 2023-03-13 15:28:07.198180

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6927bd10e170'
down_revision = 'c45d23518e0d'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('GlobalState', 'last_roster_spreadsheet', new_column_name='tms_spreadsheet_id')
    op.alter_column('GlobalState', 'last_fetched_time', new_column_name='roster_last_fetched_time')


def downgrade():
    op.alter_column('GlobalState', 'tms_spreadsheet_id', new_column_name='last_roster_spreadsheet')
    op.alter_column('GlobalState', 'roster_last_fetched_time', new_column_name='last_fetched_time')

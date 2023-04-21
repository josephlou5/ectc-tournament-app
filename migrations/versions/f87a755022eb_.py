"""Add separate template id and subject for blast notifications

Revision ID: f87a755022eb
Revises: faec307ede01
Create Date: 2023-04-20 19:04:36.025101

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f87a755022eb'
down_revision = 'faec307ede01'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "GlobalState",
        "mailchimp_template_id",
        new_column_name="mailchimp_match_template_id",
    )
    op.alter_column(
        "GlobalState",
        "mailchimp_subject",
        new_column_name="mailchimp_match_subject",
    )
    with op.batch_alter_table("GlobalState", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mailchimp_blast_template_id", sa.String(), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("mailchimp_blast_subject", sa.String(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("GlobalState", schema=None) as batch_op:
        batch_op.drop_column("mailchimp_blast_subject")
        batch_op.drop_column("mailchimp_blast_template_id")
    op.alter_column(
        "GlobalState",
        "mailchimp_match_subject",
        new_column_name="mailchimp_subject",
    )
    op.alter_column(
        "GlobalState",
        "mailchimp_match_template_id",
        new_column_name="mailchimp_template_id",
    )

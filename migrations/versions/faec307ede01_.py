"""Split team code into division and team number

Revision ID: faec307ede01
Revises: 41e45d919081
Create Date: 2023-04-19 14:03:13.749139

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'faec307ede01'
down_revision = '41e45d919081'
branch_labels = None
depends_on = None


def _split_team_codes(connection, table):
    for row_id, team_code in connection.execute(
        sa.select(table.c.id, table.c.code)
    ):
        suffix_nums = []
        for c in reversed(team_code):
            if not c.isdigit():
                break
            suffix_nums.append(c)
        division = team_code[: -len(suffix_nums)].strip()
        team_number = int("".join(reversed(suffix_nums)))
        connection.execute(
            table.update()
            .where(table.c.id == row_id)
            .values(division=division, number=team_number)
        )


def _combine_team_codes(connection, table):
    for row_id, division, team_number in connection.execute(
        sa.select(table.c.id, table.c.division, table.c.team_number)
    ):
        team_code = f"{division}{team_number}"
        connection.execute(
            table.update().where(table.c.id == row_id).values(code=team_code)
        )


def upgrade():
    connection = op.get_bind()

    # add the new columns (allow null)
    with op.batch_alter_table("Teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("division", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    # split the 'code' column into the division and team number
    teams_table = sa.Table(
        "Teams",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.VARCHAR()),
        sa.Column("division", sa.VARCHAR()),
        sa.Column("number", sa.Integer),
    )
    _split_team_codes(connection, teams_table)

    # edit the table
    with op.batch_alter_table("Teams", schema=None) as batch_op:
        # remove the old column and unique constraint
        batch_op.drop_constraint("_school_team_code", type_="unique")
        batch_op.drop_column("code")
        # make the new columns non-nullable
        batch_op.alter_column(
            "division", existing_type=sa.VARCHAR(), nullable=False
        )
        batch_op.alter_column(
            "number", existing_type=sa.Integer, nullable=False
        )
        # add unique constraint
        batch_op.create_unique_constraint(
            "_school_team_code", ["school_id", "division", "number"]
        )

    # do the same with the user subscriptions table
    with op.batch_alter_table("UserSubscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("division", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    subscriptions_table = sa.Table(
        "UserSubscriptions",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.VARCHAR()),
        sa.Column("division", sa.VARCHAR()),
        sa.Column("number", sa.Integer),
    )
    _split_team_codes(connection, subscriptions_table)

    # edit the table
    with op.batch_alter_table("UserSubscriptions", schema=None) as batch_op:
        # remove the old column and unique constraint
        batch_op.drop_constraint("_email_school_team_code", type_="unique")
        batch_op.drop_column("code")
        # make the new columns non-nullable
        batch_op.alter_column(
            "division", existing_type=sa.VARCHAR(), nullable=False
        )
        batch_op.alter_column(
            "number", existing_type=sa.Integer, nullable=False
        )
        # add unique constraint
        batch_op.create_unique_constraint(
            "_email_school_team_code",
            ["email", "school", "division", "number"],
        )


def downgrade():
    connection = op.get_bind()

    # add the old column (allow null)
    with op.batch_alter_table("Teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(), nullable=True))

    # combine the 'division' and 'number' columns into the 'code' column
    teams_table = sa.Table(
        "Teams",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.VARCHAR()),
        sa.Column("division", sa.VARCHAR()),
        sa.Column("number", sa.Integer),
    )
    _combine_team_codes(connection, teams_table)

    # edit the table
    with op.batch_alter_table("Teams", schema=None) as batch_op:
        # remove the new columns and unique constraint
        batch_op.drop_constraint("_school_team_code", type_="unique")
        batch_op.drop_column("number")
        batch_op.drop_column("division")
        # make the old column non-nullable
        batch_op.alter_column(
            "code", existing_type=sa.VARCHAR(), nullable=False
        )
        # add unique constraint
        batch_op.create_unique_constraint(
            "_school_team_code", ["school_id", "code"]
        )

    # do the same with the user subscriptions table
    with op.batch_alter_table("UserSubscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(), nullable=True))

    subscriptions_table = sa.Table(
        "UserSubscriptions",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.VARCHAR()),
        sa.Column("division", sa.VARCHAR()),
        sa.Column("number", sa.Integer),
    )
    _combine_team_codes(connection, subscriptions_table)

    # edit the table
    with op.batch_alter_table("UserSubscriptions", schema=None) as batch_op:
        # remove the new columns and unique constraint
        batch_op.drop_constraint("_email_school_team_code", type_="unique")
        batch_op.drop_column("number")
        batch_op.drop_column("division")
        # make the old column non-nullable
        batch_op.alter_column(
            "code", existing_type=sa.VARCHAR(), nullable=False
        )
        # add unique constraint
        batch_op.create_unique_constraint(
            "_email_school_team_code", ["email", "school", "code"]
        )

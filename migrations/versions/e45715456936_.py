"""Add first and last name to Users table

Revision ID: e45715456936
Revises: 09b93e8db926
Create Date: 2023-03-26 00:04:31.544130

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e45715456936'
down_revision = '09b93e8db926'
branch_labels = None
depends_on = None


def upgrade():
    # add the first and last name columns (allow null)
    with op.batch_alter_table("Users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("first_name", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("last_name", sa.String(), nullable=True))

    # split the 'name' column into the first and last name
    # names don't always necessary follow this pattern, but just try
    users_table = sa.Table(
        "Users",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.VARCHAR()),
        sa.Column("first_name", sa.VARCHAR()),
        sa.Column("last_name", sa.VARCHAR()),
    )
    connection = op.get_bind()
    for (user_id, name) in connection.execute(
        sa.select(users_table.c.id, users_table.c.name)
    ):
        names = name.split(" ", 1)
        if len(names) == 1:
            first_name = names[0]
            last_name = ""
        else:
            first_name, last_name = names
        connection.execute(
            users_table.update()
            .where(users_table.c.id == user_id)
            .values(first_name=first_name.strip(), last_name=last_name.strip())
        )

    # add constraints for the names columns and remove the old column
    with op.batch_alter_table("Users", schema=None) as batch_op:
        batch_op.alter_column(
            "first_name", existing_type=sa.VARCHAR(), nullable=False
        )
        batch_op.alter_column(
            "last_name", existing_type=sa.VARCHAR(), nullable=False
        )
        batch_op.drop_column("name")


def downgrade():
    # add the 'name' column (allow null)
    with op.batch_alter_table("Users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=True)
        )

    # set the 'name' column to be the concatenation of the names columns
    users_table = sa.Table(
        "Users",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("first_name", sa.VARCHAR()),
        sa.Column("last_name", sa.VARCHAR()),
        sa.Column("name", sa.VARCHAR()),
    )
    connection = op.get_bind()
    for (user_id, first_name, last_name) in connection.execute(
        sa.select(
            users_table.c.id,
            users_table.c.first_name,
            users_table.c.last_name,
        )
    ):
        full_name = f"{first_name} {last_name}".strip()
        connection.execute(
            users_table.update()
            .where(users_table.c.id == user_id)
            .values(name=full_name)
        )

    # add constraints for the 'name' column and remove the other columns
    with op.batch_alter_table("Users", schema=None) as batch_op:
        batch_op.alter_column(
            "name", existing_type=sa.VARCHAR(), nullable=False
        )
        batch_op.drop_column("first_name")
        batch_op.drop_column("last_name")

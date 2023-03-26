"""
Helper methods for the Admins table.
"""

# =============================================================================

from db._utils import query
from db.models import Admin, db

# =============================================================================


def _get(email):
    return query(Admin, {"email": email}).first()


def get_all():
    """Gets all the admins and super admins.

    Returns:
        Dict[LiteralString['super_admins'|'admins'], List[str]]:
            The emails of the admins and super admins.
    """
    super_admins = []
    admins = []
    for admin in query(Admin).all():
        if admin.is_super_admin:
            super_admins.append(admin.email)
        else:
            admins.append(admin.email)
    return {"super_admins": super_admins, "admins": admins}


def is_admin(email):
    """Returns True if the given email is an admin."""
    return _get(email) is not None


def is_super_admin(email):
    """Returns True if the given email is a super admin."""
    admin = _get(email)
    if admin is None:
        return False
    return admin.is_super_admin


def add_admin(email):
    """Adds the given email as an admin.

    Returns:
        bool: Whether the operation was successful.
    """
    if is_admin(email):
        return True
    admin = Admin(email)
    db.session.add(admin)
    db.session.commit()
    return True


def remove_admin(email):
    """Removes the given email as an admin.

    You cannot remove super admins.

    Returns:
        bool: Whether the operation was successful.
            If the email was not an admin, returns True.
    """
    admin = _get(email)
    if admin is None:
        return True
    if admin.is_super_admin:
        # cannot remove super admin
        return False
    db.session.delete(admin)
    db.session.commit()
    return True

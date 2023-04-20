"""
Helper methods for the UserSubscriptions table.
"""

# =============================================================================

from db._utils import clear_tables, query
from db.models import UserSubscription, db

# =============================================================================


def get_all_subscriptions(email):
    """Gets all the teams the given email is subscribed to."""
    return {
        (
            subscription.school,
            subscription.division,
            subscription.number,
        ): subscription
        for subscription in query(UserSubscription, {"email": email}).all()
    }


def get_all_subscribers(school_team_codes):
    """Gets all the subscribers for the given school team codes."""
    teams_subscribers = {
        school_team_code: set() for school_team_code in school_team_codes
    }
    for subscription in query(UserSubscription).all():
        school_team_code = (
            subscription.school,
            subscription.division,
            subscription.number,
        )
        if school_team_code not in teams_subscribers:
            continue
        teams_subscribers[school_team_code].add(subscription.email)
    return teams_subscribers


# =============================================================================


def clear_all_subscriptions():
    """Clears all the user subscriptions.

    Returns:
        bool: Whether the operation was successful.
    """
    clear_tables(UserSubscription)
    return True


# =============================================================================


def _get(email, school, division, team_number):
    return query(
        UserSubscription,
        {
            "email": email,
            "school": school,
            "division": division,
            "number": team_number,
        },
    ).first()


def add_team(email, school, division, team_number):
    """Subscribes the given email to the given team.

    Returns:
        bool: Whether the operation was successful.
    """
    existing = _get(email, school, division, team_number)
    if existing is not None:
        # already exists; do nothing
        return True
    # add subscription
    subscription = UserSubscription(email, school, division, team_number)
    db.session.add(subscription)
    db.session.commit()
    return True


def add_all_teams(email, school_team_codes):
    """Subscribes the given email to all the given teams.

    Returns:
        bool: Whether all the operations were successful.
    """
    existing_subscriptions = get_all_subscriptions(email)
    any_added = False
    for school_team_code in school_team_codes:
        if school_team_code in existing_subscriptions:
            continue
        any_added = True
        subscription = UserSubscription(email, *school_team_code)
        db.session.add(subscription)
    if any_added:
        db.session.commit()
    return True


def remove_team(email, school, division, team_number):
    """Unsubscribes the given email from the given team.

    Returns:
        bool: Whether the operation was successful.
    """
    existing = _get(email, school, division, team_number)
    if existing is None:
        # doesn't exist; do nothing
        return True
    db.session.delete(existing)
    db.session.commit()
    return True


def remove_school_teams(email, school):
    """Unsubscribes the given email from all the teams for the given
    school.

    Returns:
        bool: Whether all the operations were successful.
    """
    existing_school_teams = query(
        UserSubscription, {"email": email, "school": school}
    ).all()
    if len(existing_school_teams) == 0:
        # no subscriptions to remove
        return True
    for subscription in existing_school_teams:
        db.session.delete(subscription)
    db.session.commit()
    return True


def remove_division_teams(email, division):
    """Unsubscribes the given email from all the teams for the given
    division.

    Returns:
        bool: Whether all the operations were successful.
    """
    existing_division_teams = query(
        UserSubscription, {"email": email, "division": division}
    ).all()
    if len(existing_division_teams) == 0:
        # no subscriptions to remove
        return True
    for subscription in existing_division_teams:
        db.session.delete(subscription)
    db.session.commit()
    return True

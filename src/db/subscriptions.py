"""
Helper methods for the UserSubscriptions table.
"""

# =============================================================================

from db._utils import clear_tables, query
from db.models import UserSubscription, db

# =============================================================================


def get_all_teams(email):
    """Gets all the teams the given email is subscribed to."""
    return {
        (subscription.school, subscription.code): subscription
        for subscription in query(UserSubscription, {"email": email}).all()
    }


def get_subscribers(teams):
    """Gets all the subscribers for the given teams."""
    teams_subscribers = {team: set() for team in teams}
    for subscription in query(UserSubscription).all():
        school_team_code = (subscription.school, subscription.code)
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


def _get(email, school, team_code):
    return query(
        UserSubscription, {"email": email, "school": school, "code": team_code}
    ).first()


def add_team(email, school, team_code):
    """Subscribes the given email to the given team.

    Returns:
        bool: Whether the operation was successful.
    """
    existing = _get(email, school, team_code)
    if existing is not None:
        # already exists; do nothing
        return True
    # add subscription
    subscription = UserSubscription(email, school, team_code)
    db.session.add(subscription)
    db.session.commit()
    return True


def add_school_teams(email, school, team_codes):
    """Subscribes the given email to all the given teams.

    Returns:
        bool: Whether all the operations were successful.
    """
    existing_teams = get_all_teams(email)
    any_added = False
    for team_code in team_codes:
        school_team_code = (school, team_code)
        if school_team_code in existing_teams:
            continue
        any_added = True
        subscription = UserSubscription(email, school, team_code)
        db.session.add(subscription)
    if any_added:
        db.session.commit()
    return True


def remove_team(email, school, team_code):
    """Unsubscribes the given email from the given team.

    Returns:
        bool: Whether the operation was successful.
    """
    existing = _get(email, school, team_code)
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

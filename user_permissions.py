"""User Permissions module: identity and operation authorization."""


def require_authenticated_user(user_id: str) -> dict:
    """Verify that a user is signed in."""
    raise NotImplementedError


def authorize_conflict_resolution(user_id: str) -> dict:
    """Verify that a signed-in user may resolve an inventory conflict."""
    raise NotImplementedError

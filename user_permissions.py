"""User Permissions module: identity and operation authorization."""


def require_authenticated_user(user_id: str) -> dict:
    """Verify that a user is signed in."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise PermissionError("An authenticated user is required.")
    return {"user_id": user_id}


def authorize_conflict_resolution(user_id: str) -> dict:
    """Verify that a signed-in user may resolve an inventory conflict."""
    raise NotImplementedError

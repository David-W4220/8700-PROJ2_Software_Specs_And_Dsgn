# Authentication & permission-checking interfaces.
from typing import Any

def authenticate(authorization: str | None) -> dict[str, Any]:
  #Return the authenticated user from an authorization header.
    raise NotImplementedError


def authorize(user_id: str, action: str) -> None:    
  #Check whether a user is allowed to perform an action.
    raise NotImplementedError

from fastapi import HTTPException, status
from app.modules.local_data_storage import get_user

def authenticate(authorization: str | None) -> dict:
    """
    Authenticate a development Bearer token. 
    For this project token value = user ID like "Authorization: Bearer crew-01"
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header.",)

    parts = authorization.strip().split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format. Use Bearer <token>.",)

    user_id = parts[1]
    user = get_user(user_id)

    if user is None or not user["active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive user.",)

    return user


def authorize(user_id: str, action: str) -> bool:
    #Check whether the user can perform the requested inventory action.
    user = get_user(user_id)

    if user is None or not user["active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive user.")

    role = user["role"]
    normalized_action = str(action).lower().replace("-", "_").replace(" ", "_")

    if role == "Station Inventory Crew": #can look up and update inventory for the two implemented slices.
        if "inventory" in normalized_action:
            return True

    if role == "Admin": return True

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User isn't authorized for this action!",)

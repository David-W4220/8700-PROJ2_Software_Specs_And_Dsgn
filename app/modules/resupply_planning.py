#Resupply planning interfaces
from typing import Any

def get_resupply_needs() -> list[dict[str, Any]]:
    #Return items below minimum stock with their importance
    raise NotImplementedError


def check_capacity(mission_id: str, cargo_lines: list[dict[str, Any]]) -> dict[str, Any]:
    #Calculate cargo weight and volume and report whether both limits are met
    raise NotImplementedError

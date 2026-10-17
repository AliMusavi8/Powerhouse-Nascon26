"""Five-tier RBAC as a policy matrix (FR-5.1).

POLICY[action][role] = scope. A role absent from an action is denied. Scopes:
  platform         - anything (super admin)
  tenant           - target belongs to the principal's tenant
  own_league       - target league is the principal's league
  own_club         - target club is the principal's club
  own_club_player  - target player belongs to the principal's club
  self             - target player is the principal
Tenant isolation is checked first for every non-platform scope.
"""
from ..errors import ApiError

ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")
_ALL_TENANT = {"super_admin": "platform", "league_organizer": "tenant", "club_manager": "tenant",
               "player": "tenant", "viewer": "tenant"}

POLICY: dict[str, dict[str, str]] = {
    "tenant.create": {"super_admin": "platform"},
    "platform.config": {"super_admin": "platform"},
    "league.fixtures.write": {"super_admin": "platform", "league_organizer": "own_league"},
    "match.score.write": {"super_admin": "platform", "league_organizer": "own_league"},
    "match.pin_product": {"super_admin": "platform", "league_organizer": "own_league", "club_manager": "tenant"},
    "club.roster.write": {"super_admin": "platform", "club_manager": "own_club"},
    "club.products.write": {"super_admin": "platform", "club_manager": "own_club"},
    "player.update": {"super_admin": "platform", "club_manager": "own_club_player", "player": "self"},
    "club.read": dict(_ALL_TENANT),
    "league.read": dict(_ALL_TENANT),
    "store.read": dict(_ALL_TENANT),
    "store.buy": {"super_admin": "platform", "league_organizer": "tenant", "club_manager": "tenant",
                  "player": "tenant", "viewer": "tenant"},
    "order.manage": {"super_admin": "platform", "club_manager": "own_club"},
}


def forbidden(message: str = "You do not have permission to perform this action.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def allowed(principal: dict, action: str, target: dict | None = None) -> bool:
    scope = POLICY.get(action, {}).get(principal.get("role"))
    if scope is None:
        return False
    if scope == "platform":
        return True
    target = target or {}
    if target.get("tenant_id") is not None and target.get("tenant_id") != principal.get("tenant_id"):
        return False
    if scope == "tenant":
        return target.get("tenant_id") == principal.get("tenant_id")
    if scope == "own_league":
        return target.get("league_id") is not None and target.get("league_id") == principal.get("league_id")
    if scope == "own_club":
        return target.get("club_id") is not None and target.get("club_id") == principal.get("club_id")
    if scope == "own_club_player":
        return target.get("player_club_id") is not None and target.get("player_club_id") == principal.get("club_id")
    if scope == "self":
        return target.get("player_id") is not None and target.get("player_id") == principal.get("player_id")
    return False


def require(principal: dict, action: str, target: dict | None = None) -> None:
    if not allowed(principal, action, target):
        raise forbidden()

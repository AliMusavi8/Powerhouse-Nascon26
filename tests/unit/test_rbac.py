import time

import jwt
import pytest

from app import auth, config
from app.domain import rbac
from app.errors import ApiError

ADMIN = {"role": "super_admin"}
ORG = {"role": "league_organizer", "tenant_id": "ta", "league_id": "l1"}
MGR = {"role": "club_manager", "tenant_id": "ta", "club_id": "c1"}
PLY = {"role": "player", "tenant_id": "ta", "club_id": "c1", "player_id": "p1"}
VWR = {"role": "viewer", "tenant_id": "ta"}


def test_policy_matrix_negative_cases():
    own_league, other_league, foreign = {"tenant_id": "ta", "league_id": "l1"}, {"tenant_id": "ta", "league_id": "l2"}, \
        {"tenant_id": "tb", "league_id": "l9"}
    assert rbac.allowed(ORG, "league.fixtures.write", own_league)
    assert not rbac.allowed(ORG, "league.fixtures.write", other_league)
    assert not rbac.allowed(ORG, "league.fixtures.write", foreign)
    assert rbac.allowed(ADMIN, "league.fixtures.write", foreign)
    for who in (MGR, PLY, VWR):
        assert not rbac.allowed(who, "league.fixtures.write", own_league)
    assert rbac.allowed(MGR, "club.roster.write", {"tenant_id": "ta", "club_id": "c1"})
    assert not rbac.allowed(MGR, "club.roster.write", {"tenant_id": "ta", "club_id": "c2"})
    assert rbac.allowed(MGR, "player.update", {"tenant_id": "ta", "player_id": "p1", "player_club_id": "c1"})
    assert not rbac.allowed(MGR, "player.update", {"tenant_id": "ta", "player_id": "p2", "player_club_id": "c2"})
    assert rbac.allowed(PLY, "player.update", {"tenant_id": "ta", "player_id": "p1", "player_club_id": "c1"})
    assert not rbac.allowed(PLY, "player.update", {"tenant_id": "ta", "player_id": "p2", "player_club_id": "c1"})
    assert rbac.allowed(VWR, "club.read", {"tenant_id": "ta", "club_id": "c2"})
    assert not rbac.allowed(VWR, "club.read", {"tenant_id": "tb", "club_id": "c9"})
    for who in (ORG, MGR, PLY, VWR):
        assert not rbac.allowed(who, "platform.config")
        assert not rbac.allowed(who, "tenant.create")
    assert not rbac.allowed({"role": "hacker"}, "club.read", {"tenant_id": "ta"})
    with pytest.raises(ApiError) as e:
        rbac.require(VWR, "tenant.create")
    assert e.value.status == 403 and e.value.code == "FORBIDDEN"


def test_tokens():
    user = {"user_id": "u", "role": "viewer", "tenant_id": "ta"}
    tok = auth.issue_token(user)
    assert auth.decode_token(tok)["role"] == "viewer"
    expired = jwt.encode({"sub": "u", "role": "viewer", "exp": int(time.time()) - 10}, config.JWT_SECRET, "HS256")
    for bad in (expired, tok[:-3] + "abc", "x.y.z",
                jwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 60}, "wrong", "HS256"),
                jwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 60}, None, "none")):
        with pytest.raises(ApiError) as e:
            auth.decode_token(bad)
        assert e.value.status == 401 and e.value.code == "UNAUTHENTICATED"

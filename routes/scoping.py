
"""FastAPI routes for customer-facing AI project scoping."""

import hashlib
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.auth_middleware import get_optional_current_user
from models.user import User
from schemas.scoping import ScopingRequest, ScopingResponse
from services.ai_scoping_service import authorize_session_access, generate_scope
from utils.client_identity import get_client_ip


logger = logging.getLogger(__name__)
_AI_BUDGET_SCRIPT = """
for i = 1, 3 do
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  local limit = tonumber(ARGV[i])
  if current >= limit then
    return {0, math.max(1, redis.call('TTL', KEYS[i]))}
  end
end
for i = 1, 3 do
  local key = KEYS[i]
  local count = redis.call('INCR', key)
  if count == 1 then redis.call('EXPIRE', key, 86400) end
end
return {1, 0}
"""
_LOCAL_AI_BUDGETS: dict[tuple[str, str], tuple[int, float]] = {}
_LOCAL_AI_BUDGET_LOCK = threading.Lock()

router = APIRouter(
    prefix="/api/scoping",
    tags=["AI Scoping"],
)


@router.post(
    "/",
    response_model=ScopingResponse,
    status_code=status.HTTP_200_OK,
    summary="Create or continue an AI project scoping session",
)
async def create_or_continue_scoping_session(
    request: Request,
    payload: ScopingRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
) -> ScopingResponse:
    """
    Generate an editable project scope.

    - Without session_id: creates a new conversation.
    - With session_id: continues an existing conversation.
    - AI fallback is handled by ai_scoping_service.
    """

    try:
        owner_id = user.id if user else None
        session = authorize_session_access(
            db,
            payload,
            owner_user_id=owner_id,
            guest_capability=payload.session_token,
        )
        await _reserve_ai_budget(request, owner_id, session)
        return generate_scope(
            db,
            payload,
            owner_user_id=owner_id,
            guest_capability=payload.session_token,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scoping session is unavailable. Please start a new session.",
        ) from exc

    except SQLAlchemyError as exc:
        try:
            db.rollback()
        except SQLAlchemyError:
            logger.exception("Database rollback failed during AI scoping.")
        logger.exception("Database error while generating project scope.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scoping is temporarily unavailable. Please try again.",
        ) from exc


async def _reserve_ai_budget(request, owner_id, session) -> None:
    """Enforce shared daily account/session/global AI request budgets."""
    from config.settings import get_settings

    settings = get_settings()
    peer_ip = get_client_ip(request, settings.trusted_proxy_cidrs)
    identity = f"user:{owner_id}" if owner_id is not None else f"guest-ip:{peer_ip}"
    identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    if session is not None and session.guest_capability_hash:
        session_part = f"guest:{session.guest_capability_hash}"
    elif session is not None:
        session_part = f"account:{owner_id}:session:{session.id}"
    else:
        # A new random conversation ID cannot create a fresh account budget.
        session_part = identity
    session_hash = hashlib.sha256(session_part.encode("utf-8")).hexdigest()
    client = getattr(request.app.state, "rate_limit_redis", None)
    if client is not None:
        try:
            allowed, retry = await _run_budget_script(
                client,
                identity_hash,
                session_hash,
                settings.ai_account_daily_limit,
                settings.ai_session_daily_limit,
                settings.ai_global_daily_limit,
                settings.ai_budget_namespace,
            )
        except RedisError as exc:
            if settings.environment.lower() == "production":
                raise HTTPException(503, "AI usage protection is unavailable.") from exc
            allowed, retry = _reserve_local(identity_hash, session_hash, settings)
    elif settings.environment.lower() == "production":
        raise HTTPException(503, "AI usage protection is unavailable.")
    else:
        allowed, retry = _reserve_local(identity_hash, session_hash, settings)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="The project scoping usage limit has been reached. Please try again later.",
            headers={"Retry-After": str(max(1, retry))},
        )


async def _run_budget_script(
    client,
    identity_hash,
    session_hash,
    identity_limit,
    session_limit,
    global_limit,
    namespace="agencyforge",
):
    prefix = f"{namespace}:ai-budget:{{shared}}"
    result = await client.eval(
        _AI_BUDGET_SCRIPT,
        3,
        f"{prefix}:identity:{identity_hash}",
        f"{prefix}:session:{session_hash}",
        f"{prefix}:global",
        identity_limit,
        session_limit,
        global_limit,
    )
    return int(result[0]) == 1, int(result[1])


def _reserve_local(identity_hash, session_hash, settings):
    with _LOCAL_AI_BUDGET_LOCK:
        monotonic_now = time.monotonic()
        for key, (_, expiry) in list(_LOCAL_AI_BUDGETS.items()):
            if expiry <= monotonic_now:
                _LOCAL_AI_BUDGETS.pop(key, None)
        keys = [
            ("identity", identity_hash),
            ("session", session_hash),
            ("global", "all"),
        ]
        records = [_LOCAL_AI_BUDGETS.get(key, (0, 0)) for key in keys]
        counts = [record[0] for record in records]
        limits = [
            settings.ai_account_daily_limit,
            settings.ai_session_daily_limit,
            settings.ai_global_daily_limit,
        ]
        for record, limit in zip(records, limits):
            if record[0] >= limit:
                return False, max(1, int(record[1] - monotonic_now))
        for key, count, record in zip(keys, counts, records):
            expiry = record[1] if count else monotonic_now + 86400
            _LOCAL_AI_BUDGETS[key] = (count + 1, expiry)
    return True, 0

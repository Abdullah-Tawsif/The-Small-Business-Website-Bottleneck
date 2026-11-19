
"""FastAPI routes for customer-facing AI project scoping."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from schemas.scoping import ScopingRequest, ScopingResponse
from services.ai_scoping_service import generate_scope


logger = logging.getLogger(__name__)

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
def create_or_continue_scoping_session(
    payload: ScopingRequest,
    db: Session = Depends(get_db),
) -> ScopingResponse:
    """
    Generate an editable project scope.

    - Without session_id: creates a new conversation.
    - With session_id: continues an existing conversation.
    - AI fallback is handled by ai_scoping_service.
    """

    try:
        return generate_scope(db, payload)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:

        try:
            db.rollback()
        except SQLAlchemyError:
            logger.exception(
                "Database rollback failed during AI scoping."
            )

        logger.exception(
            "Database error while generating project scope."
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scoping is temporarily unavailable. Please try again.",
        ) from exc

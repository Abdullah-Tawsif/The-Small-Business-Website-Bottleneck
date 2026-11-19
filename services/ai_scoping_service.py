
"""AI-powered website project scoping service."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.ai_session import AISession
from models.package import Package
from schemas.scoping import ScopingRequest, ScopingResponse


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are Scopewise, an expert website project discovery assistant.

Your job is to understand a customer's business and recommend
a practical website project scope.

Return ONLY valid JSON with these fields:

{
    "scope_summary": "A clear project summary",
    "required_pages": ["Home", "About", "Contact"],
    "required_features": ["Contact form", "Responsive design"],
    "clarifying_questions": ["What is your target audience?"],
    "recommended_package_id": 1
}

Rules:
1. Never invent business information.
2. Use only package IDs supplied in the context.
3. Include pages and features relevant to the business.
4. Keep recommendations practical and understandable.
5. Ask useful questions when information is missing.
6. Respect requirements already provided by the customer.
7. Do not invent package prices.
"""


# --------------------------------------------------
# 1. GENERAL HELPERS
# --------------------------------------------------

def clean_items(
    items: list[str] | None,
    limit: int = 50,
) -> list[str]:

    if not items:
        return []

    result = []
    seen = set()

    for item in items:

        cleaned = re.sub(
            r"\s+",
            " ",
            str(item),
        ).strip()

        normalized = cleaned.casefold()

        if not cleaned or normalized in seen:
            continue

        result.append(cleaned)
        seen.add(normalized)

        if len(result) >= limit:
            break

    return result


def get_active_packages(db: Session) -> list[Package]:
    """Return available packages in display order."""

    statement = (
        select(Package)
        .where(Package.is_active.is_(True))
        .order_by(
            Package.display_order,
            Package.id,
        )
    )

    return list(db.scalars(statement).all())


# --------------------------------------------------
# 2. DETERMINISTIC AI FALLBACK
# --------------------------------------------------

def generate_fallback_scope(
    payload: ScopingRequest,
    packages: list[Package],
) -> dict[str, Any]:
    """
    Generate useful website recommendations without an external AI API.

    Uses business keywords and customer requirements.
    """

    description = " ".join([
        payload.message or "",
        payload.business_name or "",
        payload.business_type or "",
        payload.project_description or "",
        " ".join(payload.goals),
    ]).casefold()

    # E-commerce websites
    if any(word in description for word in [
        "ecommerce",
        "e-commerce",
        "online store",
        "shopping",
        "sell online",
        "products",
    ]):

        pages = [
            "Home",
            "Shop",
            "Product Details",
            "Shopping Cart",
            "Checkout",
            "About",
            "Contact",
        ]

        features = [
            "Product management",
            "Shopping cart",
            "Online payment",
            "Order management",
            "Mobile-responsive design",
        ]

    # Booking websites
    elif any(word in description for word in [
        "booking",
        "appointment",
        "reservation",
        "clinic",
        "salon",
        "hotel",
    ]):

        pages = [
            "Home",
            "Services",
            "About",
            "Booking",
            "FAQs",
            "Contact",
        ]

        features = [
            "Booking system",
            "Appointment notifications",
            "Service management",
            "Contact form",
            "Mobile-responsive design",
        ]

    # Portfolio websites
    elif any(word in description for word in [
        "portfolio",
        "photographer",
        "designer",
        "freelancer",
        "creative",
    ]):

        pages = [
            "Home",
            "Portfolio",
            "About",
            "Services",
            "Testimonials",
            "Contact",
        ]

        features = [
            "Project gallery",
            "Image portfolio",
            "Contact form",
            "Social media integration",
            "Mobile-responsive design",
        ]

    # Restaurant websites
    elif any(word in description for word in [
        "restaurant",
        "cafe",
        "café",
        "food",
        "menu",
    ]):

        pages = [
            "Home",
            "Menu",
            "About",
            "Gallery",
            "Location",
            "Contact",
        ]

        features = [
            "Menu management",
            "Online reservation",
            "Opening hours",
            "Location map",
            "Mobile-responsive design",
        ]

    # General business website
    else:

        pages = [
            "Home",
            "About",
            "Products / Services",
            "FAQs",
            "Contact",
        ]

        features = [
            "Mobile-responsive design",
            "Contact form",
            "Search engine optimization",
            "Social media integration",
        ]

    # Preserve requirements already supplied by the customer.
    pages = clean_items(
        payload.required_pages + pages,
        30,
    )

    features = clean_items(
        payload.required_features + features,
        50,
    )

    business = (
        payload.business_name
        or payload.business_type
        or "your business"
    )

    goals = ", ".join(payload.goals[:3])

    if not goals:
        goals = "build an effective online presence"

    summary = (
        f"A responsive website for {business}, "
        f"focused on {goals}. "
        f"The suggested first release includes "
        f"{len(pages)} pages and "
        f"{len(features)} key features. "
        f"The requirements can be refined before development."
    )

    questions = []

    if not payload.business_type:
        questions.append(
            "What type of business or organization is this website for?"
        )

    if not payload.project_description:
        questions.append(
            "What should visitors accomplish on your website?"
        )

    if not payload.preferred_timeline:
        questions.append(
            "When would you ideally like your website completed?"
        )

    if payload.budget_min is None and payload.budget_max is None:
        questions.append(
            "Do you have an approximate project budget?"
        )

    if not payload.current_website:
        questions.append(
            "Is this a new website or a redesign of an existing website?"
        )

    # Recommend an available package deterministically.
    recommended_package_id = None

    if packages:

        ordered = sorted(
            packages,
            key=lambda package: (
                package.max_price,
                package.display_order,
                package.id,
            ),
        )

        complexity = len(pages) + len(features) * 0.7

        if complexity >= 18 and len(ordered) > 1:
            recommended_package_id = ordered[-1].id
        else:
            recommended_package_id = ordered[0].id

    return {
        "scope_summary": summary,
        "required_pages": pages,
        "required_features": features,
        "clarifying_questions": questions[:5],
        "recommended_package_id": recommended_package_id,
    }


# --------------------------------------------------
# 3. EXTERNAL AI PROVIDER
# --------------------------------------------------

def generate_external_ai_scope(
    history: list[dict[str, Any]],
    packages: list[Package],
) -> tuple[dict[str, Any], str, int, int]:
    """
    Call an OpenAI-compatible Chat Completions API.

    Requires OPENAI_API_KEY.
    """

    api_key = os.getenv(
        "OPENAI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError("AI API key is not configured.")

    model = os.getenv(
        "OPENAI_MODEL",
        "gpt-4o-mini",
    )

    base_url = os.getenv(
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1",
    ).rstrip("/")

    endpoint = base_url + "/chat/completions"

    # Only provide real, active packages to the AI.
    package_context = [
        {
            "id": package.id,
            "name": package.name,
            "description": package.description,
            "features": package.features or [],
        }
        for package in packages
    ]

    messages = [
        {
            "role": "system",
            "content": (
                SYSTEM_PROMPT
                + "\nAvailable packages:\n"
                + json.dumps(package_context)
            ),
        }
    ]

    # Maintain a manageable conversation context.
    for item in history[-16:]:

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if not isinstance(content, str):
            content = json.dumps(content)

        messages.append({
            "role": role,
            "content": content,
        })

    request_body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {
            "type": "json_object",
        },
    }

    encoded_body = json.dumps(
        request_body,
    ).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=encoded_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    timeout = float(
        os.getenv(
            "AI_SCOPING_TIMEOUT_SECONDS",
            "18",
        )
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

    raw_content = result["choices"][0]["message"]["content"]

    ai_result = json.loads(raw_content)

    if not isinstance(ai_result, dict):
        raise ValueError("AI provider returned invalid JSON.")

    valid_package_ids = {
        package.id for package in packages
    }

    recommendation = ai_result.get(
        "recommended_package_id"
    )

    try:
        recommendation = (
            int(recommendation)
            if recommendation is not None
            else None
        )
    except (TypeError, ValueError):
        recommendation = None

    if recommendation not in valid_package_ids:
        recommendation = None

    proposal = {
        "scope_summary": str(
            ai_result.get("scope_summary")
            or "Your initial project scope is ready."
        )[:3000],

        "required_pages": clean_items(
            ai_result.get("required_pages") or [],
            30,
        ),

        "required_features": clean_items(
            ai_result.get("required_features") or [],
            50,
        ),

        "clarifying_questions": clean_items(
            ai_result.get("clarifying_questions") or [],
            8,
        ),

        "recommended_package_id": recommendation,
    }

    usage = result.get("usage") or {}

    prompt_tokens = int(
        usage.get("prompt_tokens", 0)
    )

    completion_tokens = int(
        usage.get("completion_tokens", 0)
    )

    return (
        proposal,
        model,
        prompt_tokens,
        completion_tokens,
    )


# --------------------------------------------------
# 4. MAIN SCOPING SERVICE
# --------------------------------------------------

def generate_scope(
    db: Session,
    payload: ScopingRequest,
) -> ScopingResponse:
    """
    Generate a customer project scope.

    Workflow:
    1. Create or retrieve an AI session.
    2. Store customer input.
    3. Generate AI recommendations.
    4. Use deterministic fallback when necessary.
    5. Store the assistant response.
    6. Save session usage statistics.
    7. Return structured scope information.
    """

    started_at = time.monotonic()

    # Retrieve an existing conversation.
    if payload.session_id:

        session = db.get(
            AISession,
            payload.session_id,
        )

        if session is None:
            raise ValueError(
                "Scoping session not found. Please start a new session."
            )

    else:

        session = AISession(
            conversation_history=[],
            status="active",
        )

        db.add(session)
        db.flush()

    # Retrieve currently available packages.
    packages = get_active_packages(db)

    # Load previous conversation messages.
    history = list(
        session.conversation_history or []
    )

    # Store the latest customer input.
    user_content = payload.model_dump(
        mode="json",
        exclude={"session_id"},
    )

    history.append({
        "role": "user",
        "content": user_content,
    })

    # Generate AI scope or deterministic fallback.
    try:

        proposal, model_name, prompt_tokens, completion_tokens = (
            generate_external_ai_scope(
                history,
                packages,
            )
        )

        provider = "openai-compatible"
        fallback_used = False

    except Exception as exc:

        logger.warning(
            "External AI unavailable; using deterministic fallback: %s",
            type(exc).__name__,
        )

        proposal = generate_fallback_scope(
            payload,
            packages,
        )

        provider = "deterministic"
        model_name = "deterministic-fallback"

        prompt_tokens = 0
        completion_tokens = 0

        fallback_used = True

    # Append the assistant response.
    history.append({
        "role": "assistant",
        "content": proposal,
    })

    # Persist conversation history and metadata.
    session.conversation_history = history

    session.provider = provider
    session.model_name = model_name

    session.prompt_tokens = prompt_tokens
    session.completion_tokens = completion_tokens

    session.total_tokens = (
        prompt_tokens + completion_tokens
    )

    session.duration_ms = max(
        0,
        int(
            (time.monotonic() - started_at) * 1000
        ),
    )

    session.fallback_used = fallback_used
    session.status = "active"

    try:

        db.add(session)
        db.commit()
        db.refresh(session)

    except Exception:
        db.rollback()
        raise

    # Return the API response.
    return ScopingResponse(
        session_id=session.id,
        **proposal,
    )

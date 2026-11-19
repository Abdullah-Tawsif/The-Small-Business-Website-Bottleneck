
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy.orm import Session

from models.package import Package


# ==================================================
# 1. PRICING CONFIGURATION
# ==================================================

# The package price includes up to five website pages.
INCLUDED_PAGE_COUNT = 5

# Cost per additional page (BDT).
EXTRA_PAGE_MIN_PRICE = Decimal("1000.00")
EXTRA_PAGE_MAX_PRICE = Decimal("2000.00")


# Additional feature pricing (BDT).
# These are adjustable practice pricing rules.

FEATURE_ADD_ON_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "shopping cart": (
        Decimal("4000.00"),
        Decimal("7000.00"),
    ),
    "online payment": (
        Decimal("3000.00"),
        Decimal("6000.00"),
    ),
    "booking system": (
        Decimal("5000.00"),
        Decimal("9000.00"),
    ),
    "inventory management": (
        Decimal("3000.00"),
        Decimal("6000.00"),
    ),
    "multilingual support": (
        Decimal("2000.00"),
        Decimal("4000.00"),
    ),
    "live chat": (
        Decimal("1500.00"),
        Decimal("3000.00"),
    ),
    "search and filtering": (
        Decimal("2000.00"),
        Decimal("4000.00"),
    ),
    "user accounts": (
        Decimal("2500.00"),
        Decimal("5000.00"),
    ),
    "subscription system": (
        Decimal("5000.00"),
        Decimal("9000.00"),
    ),
}


# ==================================================
# 2. HELPER FUNCTIONS
# ==================================================

def normalize_name(value: str) -> str:
    """
    Normalizes feature and page names
    for consistent comparisons.
    """

    return " ".join(value.strip().casefold().split())


def clean_unique_items(items: Sequence[str] | None) -> list[str]:
    """
    Removes blank and duplicate entries
    while preserving the original spelling.
    """

    if not items:
        return []

    result = []
    seen = set()

    for item in items:

        cleaned = item.strip()

        if not cleaned:
            continue

        normalized = normalize_name(cleaned)

        if normalized not in seen:
            result.append(cleaned)
            seen.add(normalized)

    return result


# ==================================================
# 3. MAIN PRICING FUNCTION
# ==================================================

def calculate_project_estimate(
    db: Session,
    package_id: int,
    required_pages: Sequence[str] | None = None,
    required_features: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Calculates a website development price estimate.

    Uses:
    - Selected package base price
    - Additional page charges
    - Additional feature charges
    - Existing package features

    Unknown features are flagged for manual quotation.
    """

    # --------------------------------------------------
    # A. FIND SELECTED PACKAGE
    # --------------------------------------------------

    package = db.get(Package, package_id)

    if package is None:
        raise ValueError(
            f"Package with ID {package_id} does not exist."
        )

    if not package.is_active:
        raise ValueError(
            "Selected package is currently unavailable."
        )

    # --------------------------------------------------
    # B. CLEAN CUSTOMER REQUIREMENTS
    # --------------------------------------------------

    pages = clean_unique_items(required_pages)

    features = clean_unique_items(required_features)

    # --------------------------------------------------
    # C. GET BASE PACKAGE PRICE
    # --------------------------------------------------

    base_min = package.min_price
    base_max = package.max_price

    # --------------------------------------------------
    # D. CALCULATE ADDITIONAL PAGE COST
    # --------------------------------------------------

    total_pages = len(pages)

    extra_page_count = max(
        0,
        total_pages - INCLUDED_PAGE_COUNT,
    )

    extra_pages_min = (
        EXTRA_PAGE_MIN_PRICE * extra_page_count
    )

    extra_pages_max = (
        EXTRA_PAGE_MAX_PRICE * extra_page_count
    )

    # --------------------------------------------------
    # E. IDENTIFY INCLUDED FEATURES
    # --------------------------------------------------

    included_features = {
        normalize_name(feature)
        for feature in (package.features or [])
    }

    feature_min_total = Decimal("0.00")
    feature_max_total = Decimal("0.00")

    feature_breakdown = []
    unpriced_features = []

    # --------------------------------------------------
    # F. CALCULATE ADDITIONAL FEATURE COSTS
    # --------------------------------------------------

    for feature in features:

        normalized = normalize_name(feature)

        # Do not charge for features already included
        if normalized in included_features:
            continue

        prices = FEATURE_ADD_ON_PRICES.get(normalized)

        # Unknown feature requires manual quotation
        if prices is None:
            unpriced_features.append(feature)
            continue

        minimum, maximum = prices

        feature_min_total += minimum
        feature_max_total += maximum

        feature_breakdown.append({
            "feature": feature,
            "minimum_price": minimum,
            "maximum_price": maximum,
        })

    # --------------------------------------------------
    # G. CALCULATE FINAL ESTIMATE
    # --------------------------------------------------

    estimated_min = (
        base_min
        + extra_pages_min
        + feature_min_total
    )

    estimated_max = (
        base_max
        + extra_pages_max
        + feature_max_total
    )

    # --------------------------------------------------
    # H. RETURN PRICING BREAKDOWN
    # --------------------------------------------------

    return {
        "package_id": package.id,
        "package_name": package.name,
        "currency": package.currency,

        "base_min_price": base_min,
        "base_max_price": base_max,

        "total_pages": total_pages,
        "extra_page_count": extra_page_count,

        "extra_pages_min_price": extra_pages_min,
        "extra_pages_max_price": extra_pages_max,

        "feature_breakdown": feature_breakdown,

        "additional_features_min_price": feature_min_total,
        "additional_features_max_price": feature_max_total,

        "unpriced_features": unpriced_features,

        "estimated_min_price": estimated_min,
        "estimated_max_price": estimated_max,

        "requires_manual_quote": bool(unpriced_features),
    }

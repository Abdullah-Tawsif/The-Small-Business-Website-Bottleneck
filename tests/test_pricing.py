"""Unit tests for services.pricing_service.calculate_project_estimate.

The service only needs ``Session.get`` for pricing calculations, so these tests
use a mocked SQLAlchemy session and never connect to or modify a database.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.pricing_service import calculate_project_estimate


@pytest.fixture

def sample_package():
    """Return an active package with predictable BDT prices."""
    return SimpleNamespace(
        id=1,
        name="Starter Website",
        currency="BDT",
        min_price=Decimal("10000.00"),
        max_price=Decimal("15000.00"),
        features=[],
        is_active=True,
    )


@pytest.fixture

def db_session(sample_package):
    """Mock the only database operation used by the pricing service."""
    session = Mock()
    session.get.return_value = sample_package
    return session


def test_base_package_price_is_used_without_additional_requirements(
    db_session,
    sample_package,
):
    result = calculate_project_estimate(db_session, package_id=1)

    assert result["package_id"] == sample_package.id
    assert result["package_name"] == sample_package.name
    assert result["currency"] == "BDT"
    assert result["base_min_price"] == Decimal("10000.00")
    assert result["base_max_price"] == Decimal("15000.00")
    assert result["estimated_min_price"] == Decimal("10000.00")
    assert result["estimated_max_price"] == Decimal("15000.00")
    assert result["total_pages"] == 0
    assert result["extra_page_count"] == 0
    assert result["feature_breakdown"] == []
    assert result["requires_manual_quote"] is False
    db_session.get.assert_called_once()


@pytest.mark.parametrize(
    ("page_count", "expected_extra_pages"),
    [
        (0, 0),
        (1, 0),
        (5, 0),
        (6, 1),
        (8, 3),
    ],
)
def test_additional_page_charges_start_after_five_unique_pages(
    db_session,
    page_count,
    expected_extra_pages,
):
    pages = [f"Page {number}" for number in range(page_count)]

    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_pages=pages,
    )

    assert result["total_pages"] == page_count
    assert result["extra_page_count"] == expected_extra_pages
    assert result["extra_pages_min_price"] == Decimal(
        "1000.00"
    ) * expected_extra_pages
    assert result["extra_pages_max_price"] == Decimal(
        "2000.00"
    ) * expected_extra_pages
    assert result["estimated_min_price"] == Decimal("10000.00") + (
        Decimal("1000.00") * expected_extra_pages
    )
    assert result["estimated_max_price"] == Decimal("15000.00") + (
        Decimal("2000.00") * expected_extra_pages
    )


@pytest.mark.parametrize(
    ("feature", "expected_minimum", "expected_maximum"),
    [
        ("shopping cart", "4000.00", "7000.00"),
        ("online payment", "3000.00", "6000.00"),
        ("booking system", "5000.00", "9000.00"),
        ("inventory management", "3000.00", "6000.00"),
        ("multilingual support", "2000.00", "4000.00"),
        ("live chat", "1500.00", "3000.00"),
        ("search and filtering", "2000.00", "4000.00"),
        ("user accounts", "2500.00", "5000.00"),
        ("subscription system", "5000.00", "9000.00"),
    ],
)
def test_known_feature_add_on_prices(
    db_session,
    feature,
    expected_minimum,
    expected_maximum,
):
    minimum = Decimal(expected_minimum)
    maximum = Decimal(expected_maximum)

    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=[feature],
    )

    assert result["feature_breakdown"] == [
        {
            "feature": feature,
            "minimum_price": minimum,
            "maximum_price": maximum,
        }
    ]
    assert result["additional_features_min_price"] == minimum
    assert result["additional_features_max_price"] == maximum
    assert result["estimated_min_price"] == Decimal("10000.00") + minimum
    assert result["estimated_max_price"] == Decimal("15000.00") + maximum
    assert result["unpriced_features"] == []
    assert result["requires_manual_quote"] is False


def test_feature_matching_is_case_insensitive_and_ignores_extra_whitespace(
    db_session,
):
    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=["  SHOPPING   CART  "],
    )

    assert result["feature_breakdown"] == [
        {
            "feature": "SHOPPING   CART",
            "minimum_price": Decimal("4000.00"),
            "maximum_price": Decimal("7000.00"),
        }
    ]
    assert result["estimated_min_price"] == Decimal("14000.00")
    assert result["estimated_max_price"] == Decimal("22000.00")


def test_features_already_included_in_package_are_not_charged(
    db_session,
    sample_package,
):
    sample_package.features = ["Shopping Cart", "Online Payment"]

    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=["shopping cart", "  ONLINE   PAYMENT "],
    )

    assert result["feature_breakdown"] == []
    assert result["additional_features_min_price"] == Decimal("0.00")
    assert result["additional_features_max_price"] == Decimal("0.00")
    assert result["estimated_min_price"] == Decimal("10000.00")
    assert result["estimated_max_price"] == Decimal("15000.00")
    assert result["requires_manual_quote"] is False


def test_included_and_additional_features_are_handled_separately(
    db_session,
    sample_package,
):
    sample_package.features = ["Shopping Cart"]

    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=[
            "shopping cart",
            "online payment",
            "custom booking workflow",
        ],
    )

    assert [item["feature"] for item in result["feature_breakdown"]] == [
        "online payment"
    ]
    assert result["additional_features_min_price"] == Decimal("3000.00")
    assert result["additional_features_max_price"] == Decimal("6000.00")
    assert result["unpriced_features"] == ["custom booking workflow"]
    assert result["requires_manual_quote"] is True


def test_unknown_features_are_flagged_for_manual_quotation(db_session):
    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=["AI-powered stock forecasting"],
    )

    assert result["unpriced_features"] == ["AI-powered stock forecasting"]
    assert result["feature_breakdown"] == []
    assert result["additional_features_min_price"] == Decimal("0.00")
    assert result["additional_features_max_price"] == Decimal("0.00")
    assert result["estimated_min_price"] == Decimal("10000.00")
    assert result["estimated_max_price"] == Decimal("15000.00")
    assert result["requires_manual_quote"] is True


def test_page_and_feature_costs_are_added_to_both_estimate_bounds(db_session):
    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_pages=["Home", "About", "Services", "Portfolio", "Blog", "Contact", "FAQ"],
        required_features=["shopping cart", "online payment"],
    )

    # Base package (10,000–15,000), two extra pages (2,000–4,000),
    # shopping cart (4,000–7,000), and online payment (3,000–6,000).
    assert result["extra_page_count"] == 2
    assert result["extra_pages_min_price"] == Decimal("2000.00")
    assert result["extra_pages_max_price"] == Decimal("4000.00")
    assert result["additional_features_min_price"] == Decimal("7000.00")
    assert result["additional_features_max_price"] == Decimal("13000.00")
    assert result["estimated_min_price"] == Decimal("19000.00")
    assert result["estimated_max_price"] == Decimal("32000.00")


def test_blank_and_duplicate_page_or_feature_names_are_ignored(db_session):
    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_pages=[" ", "Home", " home ", "ABOUT", "About", ""],
        required_features=["", "SHOPPING CART", "shopping   cart", "  "],
    )

    # The normalized page list contains only Home and ABOUT; the feature is
    # charged once even though it appears more than once.
    assert result["total_pages"] == 2
    assert result["extra_page_count"] == 0
    assert len(result["feature_breakdown"]) == 1
    assert result["additional_features_min_price"] == Decimal("4000.00")
    assert result["additional_features_max_price"] == Decimal("7000.00")


@pytest.mark.parametrize(
    ("required_pages", "required_features"),
    [
        (None, None),
        ([], []),
        ((), ()),
    ],
)
def test_none_or_empty_requirements_produce_no_additional_charges(
    db_session,
    required_pages,
    required_features,
):
    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_pages=required_pages,
        required_features=required_features,
    )

    assert result["total_pages"] == 0
    assert result["extra_page_count"] == 0
    assert result["feature_breakdown"] == []
    assert result["unpriced_features"] == []
    assert result["estimated_min_price"] == Decimal("10000.00")
    assert result["estimated_max_price"] == Decimal("15000.00")


def test_package_with_no_feature_list_is_supported(db_session, sample_package):
    sample_package.features = None

    result = calculate_project_estimate(
        db_session,
        package_id=1,
        required_features=["live chat"],
    )

    assert result["additional_features_min_price"] == Decimal("1500.00")
    assert result["additional_features_max_price"] == Decimal("3000.00")


def test_zero_price_package_returns_zero_estimate(db_session, sample_package):
    sample_package.min_price = Decimal("0.00")
    sample_package.max_price = Decimal("0.00")

    result = calculate_project_estimate(db_session, package_id=1)

    assert result["estimated_min_price"] == Decimal("0.00")
    assert result["estimated_max_price"] == Decimal("0.00")


def test_nonexistent_package_raises_value_error(db_session):
    db_session.get.return_value = None

    with pytest.raises(ValueError, match="Package with ID 999 does not exist"):
        calculate_project_estimate(db_session, package_id=999)


def test_inactive_package_raises_value_error(db_session, sample_package):
    sample_package.is_active = False

    with pytest.raises(ValueError, match="Selected package is currently unavailable"):
        calculate_project_estimate(db_session, package_id=1)

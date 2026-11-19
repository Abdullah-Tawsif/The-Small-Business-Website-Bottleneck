
"""Idempotently seed the database with initial website development packages."""

from decimal import Decimal

from sqlalchemy import func, select

from database.database import SessionLocal, init_db
from models.package import Package


PACKAGES = [
    {
        "name": "Starter Website",
        "slug": "starter-website",
        "description": (
            "An affordable, professional website for individuals, "
            "startups, and small businesses establishing their online presence."
        ),
        "min_price": Decimal("18000.00"),
        "max_price": Decimal("30000.00"),
        "currency": "BDT",
        "features": [
            "Responsive mobile-friendly design",
            "Up to 5 website pages",
            "Contact form integration",
            "Basic on-page SEO",
            "Social media links",
            "Basic security setup",
        ],
        "is_active": True,
        "display_order": 1,
    },
    {
        "name": "Business Website",
        "slug": "business-website",
        "description": (
            "A complete business website designed to build credibility, "
            "showcase services, and generate customer inquiries."
        ),
        "min_price": Decimal("35000.00"),
        "max_price": Decimal("65000.00"),
        "currency": "BDT",
        "features": [
            "Custom responsive website design",
            "Up to 10 website pages",
            "Content management integration",
            "Advanced contact forms",
            "On-page SEO optimization",
            "Google Analytics integration",
            "Performance optimization",
        ],
        "is_active": True,
        "display_order": 2,
    },
    {
        "name": "E-commerce Website",
        "slug": "ecommerce-website",
        "description": (
            "An online store with product management, shopping cart, "
            "checkout, and payment integration for selling products online."
        ),
        "min_price": Decimal("70000.00"),
        "max_price": Decimal("150000.00"),
        "currency": "BDT",
        "features": [
            "Custom responsive online store",
            "Product catalog and categories",
            "Shopping cart and checkout",
            "Payment gateway integration",
            "Order management dashboard",
            "Inventory management",
            "Customer account management",
            "Basic e-commerce SEO",
        ],
        "is_active": True,
        "display_order": 3,
    },
    {
        "name": "Custom Web Application",
        "slug": "custom-web-application",
        "description": (
            "A tailored web application for businesses requiring "
            "custom workflows, integrations, dashboards, and advanced functionality."
        ),
        "min_price": Decimal("150000.00"),
        "max_price": Decimal("400000.00"),
        "currency": "BDT",
        "features": [
            "Custom UI and application architecture",
            "Tailored business workflows",
            "User authentication and authorization",
            "Role-based dashboards",
            "Database design and integration",
            "Third-party API integrations",
            "Custom reporting and analytics",
            "Testing and deployment support",
        ],
        "is_active": True,
        "display_order": 4,
    },
]


def seed_packages() -> None:
    """Create missing packages without modifying existing records."""

    # Ensure all application tables exist before seeding.
    init_db()

    created_count = 0

    with SessionLocal() as db:
        try:
            # Keep all package inserts in one transaction.
            with db.begin():
                existing_slugs = set(
                    db.scalars(select(Package.slug)).all()
                )

                for package_data in PACKAGES:
                    slug = package_data["slug"]

                    # Never overwrite an existing package.
                    if slug in existing_slugs:
                        continue

                    db.add(Package(**package_data))
                    existing_slugs.add(slug)
                    created_count += 1

            # The transaction has committed successfully.
            # Verify the total number of active packages.
            active_count = db.scalar(
                select(func.count())
                .select_from(Package)
                .where(Package.is_active.is_(True))
            ) or 0

        except Exception:
            db.rollback()
            print("Package seeding failed. Transaction rolled back.")
            raise

    print(f"New packages created: {created_count}")
    print(f"Active package count: {active_count}")


if __name__ == "__main__":
    seed_packages()

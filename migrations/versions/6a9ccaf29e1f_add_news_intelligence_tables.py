"""add_news_intelligence_tables

Revision ID: 6a9ccaf29e1f
Revises: f45b2abf22f4
Create Date: 2026-07-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6a9ccaf29e1f"
down_revision: Union[str, Sequence[str], None] = "f45b2abf22f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_key", sa.String(length=128), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_reliability_score", sa.Float(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "EARNINGS", "DIVIDEND", "CONTRACT_AWARD", "EXPANSION", "ACQUISITION", "LAWSUIT",
                "REGULATORY_CHANGE", "GOVERNMENT_POLICY", "OIL", "INTEREST_RATES", "INFLATION", "CURRENCY",
                "SUPPLY_CHAIN", "PRODUCTION", "GUIDANCE", "CREDIT_RATING", "EXECUTIVE_CHANGE", "BANKRUPTCY",
                "TRADING_SUSPENSION", "OTHER", name="newscategory",
            ),
            nullable=True,
        ),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column(
            "sentiment_label",
            sa.Enum("VERY_POSITIVE", "POSITIVE", "NEUTRAL", "NEGATIVE", "VERY_NEGATIVE", name="sentimentlabel"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("short_term_impact", sa.Float(), nullable=True),
        sa.Column("medium_term_impact", sa.Float(), nullable=True),
        sa.Column("long_term_impact", sa.Float(), nullable=True),
        sa.Column("price_impact_score", sa.Float(), nullable=True),
        sa.Column("risk_impact_score", sa.Float(), nullable=True),
        sa.Column("volatility_impact_score", sa.Float(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_model", sa.String(length=64), nullable=True),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["news_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_key"),
    )
    op.create_index(op.f("ix_news_events_external_key"), "news_events", ["external_key"], unique=True)
    op.create_index(op.f("ix_news_events_source"), "news_events", ["source"], unique=False)
    op.create_index(op.f("ix_news_events_published_at"), "news_events", ["published_at"], unique=False)
    op.create_index(op.f("ix_news_events_category"), "news_events", ["category"], unique=False)
    op.create_index(op.f("ix_news_events_duplicate_of_id"), "news_events", ["duplicate_of_id"], unique=False)

    op.create_table(
        "news_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("news_event_id", sa.Integer(), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum("COMPANY", "SECTOR", "MARKET_WIDE", "GOVERNMENT", name="newsentitytype"),
            nullable=False,
        ),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["news_event_id"], ["news_events.id"]),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_news_entities_news_event_id"), "news_entities", ["news_event_id"], unique=False)
    op.create_index(op.f("ix_news_entities_entity_type"), "news_entities", ["entity_type"], unique=False)
    op.create_index(op.f("ix_news_entities_stock_id"), "news_entities", ["stock_id"], unique=False)
    op.create_index(op.f("ix_news_entities_symbol"), "news_entities", ["symbol"], unique=False)

    op.create_table(
        "news_source_reliability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("reliability_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("articles_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name"),
    )
    op.create_index(
        op.f("ix_news_source_reliability_source_name"), "news_source_reliability", ["source_name"], unique=True
    )

    op.create_table(
        "portfolio_news_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("news_event_id", sa.Integer(), nullable=False),
        sa.Column(
            "alert_type",
            sa.Enum("UPGRADE", "DOWNGRADE", "HIGH_RISK", "MAJOR_OPPORTUNITY", name="portfolioalerttype"),
            nullable=False,
        ),
        sa.Column("severity", sa.Enum("INFO", "WARNING", "CRITICAL", name="alertseverity"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["news_event_id"], ["news_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_news_alerts_portfolio_id"), "portfolio_news_alerts", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_portfolio_news_alerts_symbol"), "portfolio_news_alerts", ["symbol"], unique=False)
    op.create_index(
        op.f("ix_portfolio_news_alerts_news_event_id"), "portfolio_news_alerts", ["news_event_id"], unique=False
    )
    op.create_index(op.f("ix_portfolio_news_alerts_alert_type"), "portfolio_news_alerts", ["alert_type"], unique=False)
    op.create_index(
        op.f("ix_portfolio_news_alerts_generated_at"), "portfolio_news_alerts", ["generated_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_portfolio_news_alerts_generated_at"), table_name="portfolio_news_alerts")
    op.drop_index(op.f("ix_portfolio_news_alerts_alert_type"), table_name="portfolio_news_alerts")
    op.drop_index(op.f("ix_portfolio_news_alerts_news_event_id"), table_name="portfolio_news_alerts")
    op.drop_index(op.f("ix_portfolio_news_alerts_symbol"), table_name="portfolio_news_alerts")
    op.drop_index(op.f("ix_portfolio_news_alerts_portfolio_id"), table_name="portfolio_news_alerts")
    op.drop_table("portfolio_news_alerts")

    op.drop_index(op.f("ix_news_source_reliability_source_name"), table_name="news_source_reliability")
    op.drop_table("news_source_reliability")

    op.drop_index(op.f("ix_news_entities_symbol"), table_name="news_entities")
    op.drop_index(op.f("ix_news_entities_stock_id"), table_name="news_entities")
    op.drop_index(op.f("ix_news_entities_entity_type"), table_name="news_entities")
    op.drop_index(op.f("ix_news_entities_news_event_id"), table_name="news_entities")
    op.drop_table("news_entities")

    op.drop_index(op.f("ix_news_events_duplicate_of_id"), table_name="news_events")
    op.drop_index(op.f("ix_news_events_category"), table_name="news_events")
    op.drop_index(op.f("ix_news_events_published_at"), table_name="news_events")
    op.drop_index(op.f("ix_news_events_source"), table_name="news_events")
    op.drop_index(op.f("ix_news_events_external_key"), table_name="news_events")
    op.drop_table("news_events")

    # Only the enums this migration created -- `alertseverity` (used by
    # portfolio_news_alerts.severity) is owned by the market_intelligence
    # migration and must not be dropped here (its own market_alerts
    # table, applied earlier and downgraded later than this one, still
    # depends on it at the point this downgrade runs).
    sa.Enum(name="portfolioalerttype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="newsentitytype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sentimentlabel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="newscategory").drop(op.get_bind(), checkfirst=True)

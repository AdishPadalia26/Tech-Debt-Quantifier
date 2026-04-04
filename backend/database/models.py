"""SQLAlchemy models for scan persistence and debt history."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.connection import Base


def generate_uuid() -> str:
    """Return a new UUID4 as string."""
    return str(uuid.uuid4())


class User(Base):
    """GitHub OAuth user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True, index=True, nullable=False)
    login = Column(String, index=True)
    name = Column(String)
    avatar_url = Column(String)
    html_url = Column(String)
    email = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    repositories = relationship("Repository", back_populates="owner")
    scans = relationship("Scan", back_populates="user")


class Repository(Base):
    """A GitHub repository being tracked."""

    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=generate_uuid)
    github_url = Column(String, unique=True, nullable=False, index=True)
    repo_name = Column(String, nullable=False)
    repo_owner = Column(String, nullable=False)
    primary_language = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    last_scanned_at = Column(DateTime)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", back_populates="repositories")

    scans = relationship(
        "Scan",
        back_populates="repository",
        order_by="Scan.created_at.desc()",
    )


class Scan(Base):
    """One complete analysis run of a repository."""

    __tablename__ = "scans"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(
        String, ForeignKey("repositories.id"), nullable=False, index=True
    )
    job_id = Column(String, unique=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="scans")

    # Core metrics
    total_cost_usd = Column(Float, nullable=False, default=0.0)
    debt_score = Column(Float, nullable=False, default=0.0)
    total_hours = Column(Float, default=0.0)
    total_sprints = Column(Float, default=0.0)

    # Category breakdown (stored as JSON)
    cost_by_category = Column(JSON)  # {code_quality: {cost, hours}, ...}

    # Rate info
    hourly_rate = Column(Float)
    rate_confidence = Column(String)

    # Repo profile snapshot
    team_size = Column(Integer)
    bus_factor = Column(Integer)
    repo_age_days = Column(Integer)
    combined_multiplier = Column(Float)
    primary_language = Column(String)
    frameworks = Column(JSON)  # ["flask", "fastapi"]

    # LLM outputs
    executive_summary = Column(Text)
    priority_actions = Column(JSON)  # list of 3 priority dicts
    roi_analysis = Column(JSON)

    # Full raw result (for re-rendering without re-running)
    raw_result = Column(JSON)

    # Metadata
    status = Column(String, default="complete")
    created_at = Column(DateTime, server_default=func.now(), index=True)
    scan_duration_seconds = Column(Float)

    # Relationships
    repository = relationship("Repository", back_populates="scans")
    debt_items = relationship(
        "DebtItem", back_populates="scan", cascade="all, delete-orphan"
    )

    # Index for fast history queries
    __table_args__ = (
        Index("ix_scans_repo_created", "repository_id", "created_at"),
    )


class DebtItem(Base):
    """Individual debt item from a scan — for trend analysis."""

    __tablename__ = "debt_items"

    id = Column(String, primary_key=True, default=generate_uuid)
    scan_id = Column(String, ForeignKey("scans.id"), nullable=False, index=True)

    # Item details
    file_path = Column(String, index=True)
    function_name = Column(String)
    category = Column(String, index=True)
    severity = Column(String)

    # Metrics
    cost_usd = Column(Float)
    hours = Column(Float)
    complexity = Column(Integer)
    churn_multiplier = Column(Float)

    created_at = Column(DateTime, server_default=func.now())

    scan = relationship("Scan", back_populates="debt_items")

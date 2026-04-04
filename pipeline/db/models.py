"""
pipeline.db.models
~~~~~~~~~~~~~~~~~~
SQLAlchemy ORM definitions mapping directly to PostgreSQL.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# We import the enums from our business models to use in string columns
# or we can just map them as strings in the DB to avoid Postgres enum type hassles.
# Here we'll map them as strings for simplicity of migrations.


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""

    pass


class PaperORM(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    pdf_storage_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # Store bibliographical info as JSONB
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    runs: Mapped[list["PipelineRunORM"]] = relationship(
        "PipelineRunORM", back_populates="paper", cascade="all, delete-orphan"
    )
    extractions: Mapped[list["ExtractionORM"]] = relationship(
        "ExtractionORM", back_populates="paper", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list["EmbeddingORM"]] = relationship(
        "EmbeddingORM", back_populates="paper", cascade="all, delete-orphan"
    )
    outputs: Mapped[list["OutputORM"]] = relationship(
        "OutputORM", back_populates="paper", cascade="all, delete-orphan"
    )


class PipelineRunORM(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    paper: Mapped["PaperORM"] = relationship("PaperORM", back_populates="runs")
    stages: Mapped[list["StageResultORM"]] = relationship(
        "StageResultORM", back_populates="run", cascade="all, delete-orphan"
    )


class StageResultORM(Base):
    __tablename__ = "stage_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    stage_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached: Mapped[bool] = mapped_column(default=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    run: Mapped["PipelineRunORM"] = relationship(
        "PipelineRunORM", back_populates="stages"
    )


class ExtractionORM(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)

    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    paper: Mapped["PaperORM"] = relationship("PaperORM", back_populates="extractions")


class EmbeddingORM(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    chunk_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # 768 dimensions for text-embedding-004 model
    embedding: Mapped[Any] = mapped_column(Vector(768), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    paper: Mapped["PaperORM"] = relationship("PaperORM", back_populates="embeddings")


class OutputORM(Base):
    __tablename__ = "outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    paper: Mapped["PaperORM"] = relationship("PaperORM", back_populates="outputs")

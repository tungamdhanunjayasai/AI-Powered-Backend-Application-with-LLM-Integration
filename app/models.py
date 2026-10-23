from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    document: Mapped["Document"] = relationship()
    nodes: Mapped[list["DocumentNode"]] = relationship(back_populates="version", cascade="all, delete-orphan")

class DocumentNode(Base):
    __tablename__ = "document_nodes"
    __table_args__ = (UniqueConstraint("version_id", "node_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    logical_key: Mapped[str] = mapped_column(String(64), index=True)
    node_key: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("document_nodes.id"), nullable=True, index=True)
    heading: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(String(30), default="section")
    body_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped["DocumentVersion"] = relationship(back_populates="nodes")
    children: Mapped[list["DocumentNode"]] = relationship(
        "DocumentNode", back_populates="parent", cascade="all, delete-orphan",
        order_by="DocumentNode.id", foreign_keys=[parent_id]
    )
    parent: Mapped["DocumentNode | None"] = relationship(
        "DocumentNode", back_populates="children", remote_side=[id], foreign_keys=[parent_id]
    )

class Selection(Base):
    __tablename__ = "selections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list["SelectionItem"]] = relationship(back_populates="selection", cascade="all, delete-orphan")

class SelectionItem(Base):
    __tablename__ = "selection_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("document_nodes.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    logical_key: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    heading_snapshot: Mapped[str] = mapped_column(Text)
    body_snapshot: Mapped[str] = mapped_column(Text)
    level_snapshot: Mapped[int] = mapped_column(Integer)
    selection: Mapped["Selection"] = relationship(back_populates="items")
    node: Mapped["DocumentNode"] = relationship()
    version: Mapped["DocumentVersion"] = relationship()

class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(150))
    prompt_version: Mapped[str] = mapped_column(String(30), default="1.0")
    status: Mapped[str] = mapped_column(String(30), default="ok")
    output_json: Mapped[dict] = mapped_column(JSON)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    selection: Mapped["Selection"] = relationship()

class GenerationSource(Base):
    __tablename__ = "generation_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generations.id"), index=True)
    selection_item_id: Mapped[int] = mapped_column(ForeignKey("selection_items.id"), index=True)
    generation: Mapped["Generation"] = relationship()
    selection_item: Mapped["SelectionItem"] = relationship()

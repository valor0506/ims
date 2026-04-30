from sqlalchemy import Column, String, DateTime, Integer, JSON, CheckConstraint
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass

# PostgreSQL ENUM types
severity_enum = ENUM('P0', 'P1', 'P2', 'P3', name='severity_enum', create_type=True)
status_enum = ENUM('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED', name='status_enum', create_type=True)

class WorkItemDB(Base):
    """
    Source of Truth table for Work Items.
    Stored in PostgreSQL with ACID guarantees.
    """
    __tablename__ = "work_items"
    
    id = Column(String(32), primary_key=True)
    component_id = Column(String(100), nullable=False, index=True)
    severity = Column(severity_enum, nullable=False)
    status = Column(status_enum, nullable=False, default='OPEN')
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # RCA stored as JSONB (PostgreSQL native JSON type)
    rca = Column(JSON, nullable=True)
    
    # MTTR calculated automatically by database
    mttr_seconds = Column(Integer, nullable=True)
    
    # Database-level constraint: Cannot close without RCA
    __table_args__ = (
        CheckConstraint(
            "(status != 'CLOSED') OR (rca IS NOT NULL AND rca->>'root_cause_category' IS NOT NULL)",
            name='rca_required_for_close'
        ),
    )
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Set
from enum import Enum

class Status(Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class InvalidTransition(Exception):
    """Raised when trying invalid state transition"""
    pass

class RCARequired(Exception):
    """Raised when trying to close without RCA"""
    pass

@dataclass
class RCA:
    """Root Cause Analysis data structure"""
    start_time: datetime
    end_time: datetime
    root_cause_category: str  # Must be: infra, code, config, dependency
    fix_applied: str
    prevention_steps: str
    
    def is_complete(self) -> bool:
        """Validate RCA completeness"""
        return all([
            self.start_time and self.end_time,
            len(self.fix_applied) >= 20,
            len(self.prevention_steps) >= 20,
            self.root_cause_category in {"infra", "code", "config", "dependency"}
        ])

@dataclass
class WorkItem:
    """
    Domain model for incident work item.
    Uses State Pattern for status transitions.
    """
    id: str
    component_id: str
    severity: str
    status: Status = Status.OPEN
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    rca: Optional[RCA] = None
    
    # Valid transitions: current_status -> {allowed_next_statuses}
    TRANSITIONS: Dict[Status, Set[Status]] = field(default_factory=lambda: {
        Status.OPEN: {Status.INVESTIGATING},
        Status.INVESTIGATING: {Status.RESOLVED, Status.OPEN},
        Status.RESOLVED: {Status.CLOSED, Status.INVESTIGATING},
        Status.CLOSED: set()  # Terminal state - no exits
    }, repr=False)
    
    def transition_to(self, new_status: Status) -> None:
        """
        State Pattern implementation.
        Validates transition, executes side effects, updates state.
        """
        # Check if transition is valid
        if new_status not in self.TRANSITIONS[self.status]:
            raise InvalidTransition(
                f"Cannot transition from {self.status.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in self.TRANSITIONS[self.status]]}"
            )
        
        # Special handling for CLOSED state
        if new_status == Status.CLOSED:
            if not self.rca or not self.rca.is_complete():
                raise RCARequired(
                    "Complete RCA required before closing. "
                    "Must include: start_time, end_time, category, fix_applied (20+ chars), prevention_steps (20+ chars)"
                )
            self.resolved_at = datetime.utcnow()
        
        # Execute transition
        self.status = new_status
    
    @property
    def mttr_seconds(self) -> Optional[float]:
        """Mean Time To Repair: created_at to resolved_at"""
        if self.resolved_at and self.created_at:
            return (self.resolved_at - self.created_at).total_seconds()
        return None
    
    def to_dict(self) -> dict:
        """Serialize for API responses"""
        return {
            "id": self.id,
            "component_id": self.component_id,
            "severity": self.severity,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "mttr_seconds": self.mttr_seconds,
            "rca": {
                "start_time": self.rca.start_time.isoformat(),
                "end_time": self.rca.end_time.isoformat(),
                "root_cause_category": self.rca.root_cause_category,
                "fix_applied": self.rca.fix_applied,
                "prevention_steps": self.rca.prevention_steps,
            } if self.rca else None
        }
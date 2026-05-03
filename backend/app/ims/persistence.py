"""
persistence.py — Fixed:
1. MongoDB ObjectId serialization crash on /incidents/{id} endpoint.
   Raw Motor documents contain _id as ObjectId — json.dumps raises TypeError.
   Fixed by converting _id to string before returning.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import WorkItemDB
from .mongo_client import raw_signals_collection
from .state_machine import WorkItem, Status, RCA
from datetime import datetime
from typing import Optional, List, Dict, Any


class WorkItemRepository:
    """
    Repository Pattern: Abstracts DB operations for Work Items.
    Translates between domain model (WorkItem) and DB model (WorkItemDB).
    """

    @staticmethod
    async def create(session: AsyncSession, work_item: WorkItem) -> WorkItemDB:
        db_item = WorkItemDB(
            id=work_item.id,
            component_id=work_item.component_id,
            severity=work_item.severity,
            status=work_item.status.value,
            created_at=work_item.created_at,
        )
        session.add(db_item)
        await session.commit()
        return db_item

    @staticmethod
    async def get_by_id(session: AsyncSession, work_item_id: str) -> Optional[WorkItem]:
        result = await session.execute(
            select(WorkItemDB).where(WorkItemDB.id == work_item_id)
        )
        db_item = result.scalar_one_or_none()
        if not db_item:
            return None
        return WorkItemRepository._to_domain(db_item)

    @staticmethod
    async def update(session: AsyncSession, work_item: WorkItem) -> None:
        result = await session.execute(
            select(WorkItemDB).where(WorkItemDB.id == work_item.id)
        )
        db_item = result.scalar_one()
        db_item.status = work_item.status.value
        db_item.resolved_at = work_item.resolved_at

        if work_item.rca:
            db_item.rca = {
                "start_time": work_item.rca.start_time.isoformat(),
                "end_time": work_item.rca.end_time.isoformat(),
                "root_cause_category": work_item.rca.root_cause_category,
                "fix_applied": work_item.rca.fix_applied,
                "prevention_steps": work_item.rca.prevention_steps,
            }

        await session.commit()

    @staticmethod
    async def get_active(session: AsyncSession) -> List[WorkItem]:
        result = await session.execute(
            select(WorkItemDB).where(WorkItemDB.status != 'CLOSED')
        )
        return [WorkItemRepository._to_domain(item) for item in result.scalars()]

    @staticmethod
    def _to_domain(db_item: WorkItemDB) -> WorkItem:
        wi = WorkItem(
            id=db_item.id,
            component_id=db_item.component_id,
            severity=db_item.severity,
            status=Status(db_item.status),
            created_at=db_item.created_at,
            resolved_at=db_item.resolved_at,
        )
        if db_item.rca:
            wi.rca = RCA(
                start_time=datetime.fromisoformat(db_item.rca["start_time"]),
                end_time=datetime.fromisoformat(db_item.rca["end_time"]),
                root_cause_category=db_item.rca["root_cause_category"],
                fix_applied=db_item.rca["fix_applied"],
                prevention_steps=db_item.rca["prevention_steps"],
            )
        return wi


class SignalRepository:
    """Repository for raw signals in MongoDB."""

    @staticmethod
    async def store(signal_doc: Dict[str, Any]) -> str:
        result = await raw_signals_collection.insert_one(signal_doc)
        return str(result.inserted_id)

    @staticmethod
    async def get_by_work_item(work_item_id: str) -> List[Dict[str, Any]]:
        cursor = raw_signals_collection.find(
            {"work_item_id": work_item_id}
        ).sort("ingested_at", -1)

        docs = await cursor.to_list(length=1000)

        # Fix: ObjectId is not JSON serializable — convert _id to string
        # Without this, /incidents/{id} crashes with TypeError on every call
        for doc in docs:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            # Also handle datetime fields Motor returns as datetime objects
            if "ingested_at" in doc and isinstance(doc["ingested_at"], datetime):
                doc["ingested_at"] = doc["ingested_at"].isoformat()

        return docs
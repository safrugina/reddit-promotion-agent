import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import ContentCandidate
from app.db.models.enums import ApprovalStatus, ValidationStatus
from app.errors import ValidationError


async def approve_candidate(session: AsyncSession, candidate_id: uuid.UUID) -> ContentCandidate:
    candidate = await session.get(ContentCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")
    if candidate.validation_status != ValidationStatus.PASS:
        raise ValidationError(
            f"Cannot approve: validation_status is {candidate.validation_status.value}, "
            "not PASS. Fix the issues and re-run 'candidate validate' first."
        )

    candidate.approval_status = ApprovalStatus.APPROVED
    await session.flush()
    await log_event(
        session,
        "APPROVED",
        project_id=candidate.project_id,
        candidate_id=str(candidate.id),
        user_action=True,
    )
    return candidate


async def reject_candidate(
    session: AsyncSession, candidate_id: uuid.UUID, reason: str | None = None
) -> ContentCandidate:
    candidate = await session.get(ContentCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    candidate.approval_status = ApprovalStatus.REJECTED
    await session.flush()
    await log_event(
        session,
        "REJECTED",
        project_id=candidate.project_id,
        candidate_id=str(candidate.id),
        reason=reason,
        user_action=True,
    )
    return candidate

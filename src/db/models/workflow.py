from sqlalchemy import String, Enum, DateTime, func
from sqlalchemy import UUID as SQL_UUID
from sqlalchemy.orm import mapped_column, Mapped
from uuid import UUID, uuid4
from datetime import datetime


from src.db.base import Base
from src.enums import WorkflowStatus


class Workflow(Base):
    __tablename__ = "workflow"

    id: Mapped[UUID] = mapped_column(SQL_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # user's original request
    instruction: Mapped[str] = mapped_column(String, nullable=False)

    # current workflow state
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), nullable=False, default=WorkflowStatus.QUEUED)

    # completed research report
    result: Mapped[str] = mapped_column(String, nullable=True)

    # failure information, if applicable
    error_message: Mapped[str] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # when execution began
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # when execution finished
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
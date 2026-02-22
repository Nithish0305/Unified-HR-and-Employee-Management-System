from pydantic import BaseModel, Field
from typing import List
from .models import Leave

class PendingLeaveListResponse(BaseModel):
    message: str = Field(..., description="Status message")
    data: List[Leave] = Field(..., description="List of pending leave requests")

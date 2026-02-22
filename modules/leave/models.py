from pydantic import BaseModel, Field
from datetime import date, datetime
from uuid import UUID
from enum import Enum
from typing import Optional


class LeaveStatus(str, Enum):
    """Enum for leave request status"""
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class LeaveCreate(BaseModel):
    """Model for creating a new leave request"""
    employee_id: str = Field(..., description="Employee ID")
    leave_type: str = Field(..., description="Type of leave (e.g., Casual, Sick, Personal)")
    start_date: date = Field(..., description="Leave start date")
    end_date: date = Field(..., description="Leave end date")
    reason: str = Field(..., description="Reason for leave request")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "leave_type": "Sick",
                "start_date": "2026-02-20",
                "end_date": "2026-02-22",
                "reason": "Medical appointment"
            }
        }


class LeaveUpdate(BaseModel):
    """Model for updating a leave request"""
    leave_type: Optional[str] = Field(None, description="Type of leave")
    start_date: Optional[date] = Field(None, description="Leave start date")
    end_date: Optional[date] = Field(None, description="Leave end date")
    reason: Optional[str] = Field(None, description="Reason for leave request")
    status: Optional[LeaveStatus] = Field(None, description="Leave status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "Approved",
                "reason": "Medical appointment updated"
            }
        }


class Leave(BaseModel):
    """Model for leave request"""
    leave_id: UUID = Field(..., description="Unique leave request ID")
    employee_id: str = Field(..., description="Employee ID")
    leave_type: str = Field(..., description="Type of leave")
    start_date: date = Field(..., description="Leave start date")
    end_date: date = Field(..., description="Leave end date")
    reason: str = Field(..., description="Reason for leave request")
    status: LeaveStatus = Field(default=LeaveStatus.PENDING, description="Leave status")
    applied_on: datetime = Field(default_factory=datetime.now, description="Date and time when leave was applied")

    class Config:
        json_schema_extra = {
            "example": {
                "leave_id": "550e8400-e29b-41d4-a716-446655440000",
                "employee_id": "emp-001",
                "leave_type": "Sick",
                "start_date": "2026-02-20",
                "end_date": "2026-02-22",
                "reason": "Medical appointment",
                "status": "Pending",
                "applied_on": "2026-02-19T10:30:00"
            }
        }


class LeaveBalanceCreate(BaseModel):
    """Model for creating leave balance"""
    employee_id: str = Field(..., description="Employee ID")
    total_leaves: int = Field(..., ge=0, description="Total leaves allocated")
    used_leaves: int = Field(default=0, ge=0, description="Leaves already used")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "total_leaves": 20,
                "used_leaves": 3
            }
        }


class LeaveBalanceUpdate(BaseModel):
    """Model for updating leave balance"""
    total_leaves: Optional[int] = Field(None, ge=0, description="Total leaves allocated")
    used_leaves: Optional[int] = Field(None, ge=0, description="Leaves already used")

    class Config:
        json_schema_extra = {
            "example": {
                "used_leaves": 5
            }
        }


class LeaveBalance(BaseModel):
    """Model for leave balance tracking"""
    employee_id: str = Field(..., description="Employee ID")
    total_leaves: int = Field(..., ge=0, description="Total leaves allocated")
    used_leaves: int = Field(default=0, ge=0, description="Leaves already used")
    remaining_leaves: int = Field(default=0, ge=0, description="Remaining leaves available")

    @classmethod
    def from_totals(cls, employee_id: str, total_leaves: int, used_leaves: int):
        """Factory method to create LeaveBalance with calculated remaining leaves"""
        return cls(
            employee_id=employee_id,
            total_leaves=total_leaves,
            used_leaves=used_leaves,
            remaining_leaves=total_leaves - used_leaves
        )

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "total_leaves": 20,
                "used_leaves": 3,
                "remaining_leaves": 17
            }
        }


class LeaveResponse(BaseModel):
    """Model for API response containing leave details"""
    message: str
    data: Leave


class LeaveBalanceResponse(BaseModel):
    """Model for API response containing leave balance details"""
    message: str
    data: LeaveBalance

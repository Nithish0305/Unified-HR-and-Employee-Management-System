from pydantic import BaseModel, Field
from datetime import datetime, date
from uuid import UUID
from enum import Enum
from typing import Optional
from decimal import Decimal


class SalaryStatus(str, Enum):
    """Enum for salary change status"""
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class PromotionStatus(str, Enum):
    """Enum for promotion status"""
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class AuditAction(str, Enum):
    """Enum for audit action types"""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    VIEW = "VIEW"


# ==================== Salary Models ====================

class SalaryCreate(BaseModel):
    """Model for creating a new salary change request"""
    employee_id: str = Field(..., description="Employee ID")
    current_salary: Decimal = Field(..., gt=0, description="Current salary amount")
    proposed_salary: Decimal = Field(..., gt=0, description="Proposed new salary amount")
    effective_date: date = Field(..., description="Date when salary change becomes effective")
    reason: Optional[str] = Field(None, description="Reason for salary change")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "current_salary": 50000,
                "proposed_salary": 55000,
                "effective_date": "2026-03-01",
                "reason": "Performance increment"
            }
        }


class SalaryUpdate(BaseModel):
    """Model for updating a salary request"""
    proposed_salary: Optional[Decimal] = Field(None, gt=0, description="Proposed salary amount")
    effective_date: Optional[date] = Field(None, description="Effective date")
    reason: Optional[str] = Field(None, description="Reason for change")
    status: Optional[SalaryStatus] = Field(None, description="Salary request status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "Approved",
                "proposed_salary": 55000
            }
        }


class Salary(BaseModel):
    """Model for salary change record"""
    salary_id: UUID = Field(..., description="Unique salary change ID")
    employee_id: str = Field(..., description="Employee ID")
    current_salary: Decimal = Field(..., gt=0, description="Current salary before change")
    proposed_salary: Decimal = Field(..., gt=0, description="Proposed new salary")
    salary_increase: Optional[Decimal] = Field(None, description="Salary increase amount (proposed - current)")
    increase_percentage: Optional[float] = Field(None, description="Percentage increase")
    effective_date: date = Field(..., description="Date when change becomes effective")
    reason: Optional[str] = Field(None, description="Reason for salary change")
    status: SalaryStatus = Field(default=SalaryStatus.PENDING, description="Salary change status")
    initiated_by: str = Field(..., description="Employee ID who initiated the request")
    approved_by: Optional[str] = Field(None, description="Employee ID who approved the request")
    approval_remarks: Optional[str] = Field(None, description="Remarks on approval/rejection")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Request creation date")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update date")
    approved_on: Optional[datetime] = Field(None, description="Date and time of approval/rejection")

    class Config:
        json_schema_extra = {
            "example": {
                "salary_id": "550e8400-e29b-41d4-a716-446655440000",
                "employee_id": "emp-001",
                "current_salary": 50000,
                "proposed_salary": 55000,
                "salary_increase": 5000,
                "increase_percentage": 10.0,
                "effective_date": "2026-03-01",
                "reason": "Performance increment",
                "status": "Pending",
                "initiated_by": "emp-002",
                "created_at": "2026-02-19T10:30:00",
                "updated_at": "2026-02-19T10:30:00"
            }
        }


class SalaryResponse(BaseModel):
    """Model for API response containing salary details"""
    message: str
    data: Salary


class SalaryListResponse(BaseModel):
    """Model for API response containing list of salaries"""
    message: str
    total: int
    data: list[Salary]


# ==================== Promotion Models ====================

class PromotionCreate(BaseModel):
    """Model for creating a promotion request"""
    employee_id: str = Field(..., description="Employee ID")
    old_role: str = Field(..., description="Current job role")
    new_role: str = Field(..., description="Promoted role")
    effective_date: date = Field(..., description="Promotion effective date")
    reason: Optional[str] = Field(None, description="Reason for promotion")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "old_role": "Senior Developer",
                "new_role": "Tech Lead",
                "effective_date": "2026-03-01",
                "reason": "Excellent performance and leadership skills"
            }
        }


class PromotionUpdate(BaseModel):
    """Model for updating a promotion request"""
    new_role: Optional[str] = Field(None, description="New role")
    effective_date: Optional[date] = Field(None, description="Effective date")
    reason: Optional[str] = Field(None, description="Reason for promotion")
    status: Optional[PromotionStatus] = Field(None, description="Promotion status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "Approved",
                "new_role": "Team Lead"
            }
        }


class Promotion(BaseModel):
    """Model for promotion record"""
    promotion_id: UUID = Field(..., description="Unique promotion ID")
    employee_id: str = Field(..., description="Employee ID")
    old_role: str = Field(..., description="Current job role")
    new_role: str = Field(..., description="Promoted job role")
    effective_date: date = Field(..., description="Promotion effective date")
    reason: Optional[str] = Field(None, description="Reason for promotion")
    status: PromotionStatus = Field(default=PromotionStatus.PENDING, description="Promotion status")
    initiated_by: str = Field(..., description="Employee ID who initiated the request")
    approved_by: Optional[str] = Field(None, description="Employee ID who approved the promotion")
    approval_remarks: Optional[str] = Field(None, description="Remarks on approval/rejection")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Request creation date")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update date")
    approved_on: Optional[datetime] = Field(None, description="Date and time of approval/rejection")

    class Config:
        json_schema_extra = {
            "example": {
                "promotion_id": "550e8400-e29b-41d4-a716-446655440001",
                "employee_id": "emp-001",
                "old_role": "Senior Developer",
                "new_role": "Tech Lead",
                "effective_date": "2026-03-01",
                "reason": "Excellent performance and leadership skills",
                "status": "Pending",
                "initiated_by": "emp-002",
                "created_at": "2026-02-19T10:30:00",
                "updated_at": "2026-02-19T10:30:00"
            }
        }


class PromotionResponse(BaseModel):
    """Model for API response containing promotion details"""
    message: str
    data: Promotion


class PromotionListResponse(BaseModel):
    """Model for API response containing list of promotions"""
    message: str
    total: int
    data: list[Promotion]


# ==================== Audit Log Models ====================

class AuditLogCreate(BaseModel):
    """Model for creating audit log entry"""
    action: AuditAction = Field(..., description="Type of action performed")
    module: str = Field(..., description="Module affected (e.g., 'salary', 'promotion')")
    record_id: str = Field(..., description="ID of the record affected")
    performed_by: str = Field(..., description="Employee ID who performed the action")
    changes: Optional[dict] = Field(None, description="Details of changes made")
    remarks: Optional[str] = Field(None, description="Additional remarks")

    class Config:
        json_schema_extra = {
            "example": {
                "action": "APPROVE",
                "module": "salary",
                "record_id": "550e8400-e29b-41d4-a716-446655440000",
                "performed_by": "EMP002",
                "remarks": "Approved based on performance review"
            }
        }


class AuditLog(BaseModel):
    """Model for audit log record"""
    audit_id: UUID = Field(..., description="Unique audit log ID")
    action: AuditAction = Field(..., description="Type of action performed")
    module: str = Field(..., description="Module affected")
    record_id: str = Field(..., description="ID of affected record")
    performed_by: str = Field(..., description="Employee who performed action")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When action was performed")
    ip_address: Optional[str] = Field(None, description="IP address of performer")
    changes: Optional[dict] = Field(None, description="Details of changes")
    remarks: Optional[str] = Field(None, description="Additional remarks")
    status: str = Field(default="SUCCESS", description="Status of action (SUCCESS/FAILED)")

    class Config:
        json_schema_extra = {
            "example": {
                "audit_id": "550e8400-e29b-41d4-a716-446655440002",
                "action": "APPROVE",
                "module": "salary",
                "record_id": "550e8400-e29b-41d4-a716-446655440000",
                "performed_by": "EMP002",
                "timestamp": "2026-02-19T10:35:00",
                "remarks": "Approved after review",
                "status": "SUCCESS"
            }
        }


class AuditLogResponse(BaseModel):
    """Model for API response containing audit log details"""
    message: str
    data: AuditLog


class AuditLogListResponse(BaseModel):
    """Model for API response containing list of audit logs"""
    message: str
    total: int
    data: list[AuditLog]


# ==================== Combined Response Models ====================

class EmployeeSalaryInfo(BaseModel):
    """Model for employee salary information"""
    employee_id: str = Field(..., description="Employee ID")
    current_salary: Decimal = Field(..., description="Current active salary")
    pending_salary_change: Optional[Salary] = Field(None, description="Pending salary change request if any")
    last_salary_change: Optional[Salary] = Field(None, description="Last approved salary change")
    last_salary_change_date: Optional[date] = Field(None, description="Date of last salary change")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "current_salary": 50000,
                "pending_salary_change": None,
                "last_salary_change_date": "2025-12-01"
            }
        }


class EmployeePromotionInfo(BaseModel):
    """Model for employee promotion information"""
    employee_id: str = Field(..., description="Employee ID")
    current_role: str = Field(..., description="Current job role")
    pending_promotion: Optional[Promotion] = Field(None, description="Pending promotion request if any")
    last_promotion: Optional[Promotion] = Field(None, description="Last approved promotion")
    last_promotion_date: Optional[date] = Field(None, description="Date of last promotion")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "current_role": "Senior Developer",
                "pending_promotion": None,
                "last_promotion_date": "2025-06-01"
            }
        }


class EmployeeCareerInfo(BaseModel):
    """Combined model for employee salary and promotion info"""
    employee_id: str = Field(..., description="Employee ID")
    salary_info: EmployeeSalaryInfo = Field(..., description="Salary information")
    promotion_info: EmployeePromotionInfo = Field(..., description="Promotion information")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "emp-001",
                "salary_info": {},
                "promotion_info": {}
            }
        }

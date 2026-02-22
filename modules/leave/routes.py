from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, date
from uuid import uuid4
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from .models import (
    Leave, LeaveCreate, LeaveUpdate, LeaveBalance, LeaveBalanceCreate,
    LeaveResponse, LeaveBalanceResponse, LeaveStatus
)

# This should be imported from your main app's dependencies
# Adjust the import path based on your project structure
from dependencies import get_current_user
from database import db
from employee_validator import validate_employee_exists


router = APIRouter(prefix="/leave", tags=["leave"])
from .schemas import PendingLeaveListResponse

# ...existing code...
@router.get("/pending-approvals", response_model=PendingLeaveListResponse)
async def list_pending_leaves(
    employee_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    List all pending leave requests (HR/Admin only).
    Optional employee_id filter for searching specific employee's requests.
    """
    allowed_roles = [UserRoles.HR, UserRoles.ADMIN]
    if current_user.get("role", "").lower() not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR or Admin can view pending leave approvals"
        )
    leaves_collection = await get_leaves_collection()
    query = {"status": LeaveStatus.PENDING}
    if employee_id:
        query["employee_id"] = employee_id
    leaves = await leaves_collection.find(query).sort("applied_on", -1).to_list(None)
    leave_list = [
        Leave(
            leave_id=leave["leave_id"],
            employee_id=leave["employee_id"],
            leave_type=leave["leave_type"],
            start_date=extract_date(leave["start_date"]),
            end_date=extract_date(leave["end_date"]),
            reason=leave["reason"],
            status=leave["status"],
            applied_on=leave["applied_on"]
        )
        for leave in leaves
    ]
    return PendingLeaveListResponse(
        message=f"Found {len(leave_list)} pending leave requests",
        data=leave_list
    )

@router.post("/pending-approvals", response_model=PendingLeaveListResponse)
async def handle_pending_leave_action(
    leave_id: str,
    action: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    allowed_roles = [UserRoles.HR, UserRoles.ADMIN]
    if current_user.get("role", "").lower() not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR or Admin can approve/reject leaves"
        )
    leaves_collection = await get_leaves_collection()
    leave_doc = await leaves_collection.find_one({"leave_id": leave_id, "status": LeaveStatus.PENDING})
    if not leave_doc:
        raise HTTPException(status_code=404, detail="Pending leave request not found")
    if action == "approve":
        updated_doc = await leaves_collection.find_one_and_update(
            {"leave_id": leave_id},
            {"$set": {
                "status": LeaveStatus.APPROVED,
                "approved_by": current_user.get("employee_id"),
                "approved_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }},
            return_document=True
        )
    elif action == "reject":
        if not reason:
            raise HTTPException(status_code=400, detail="Reason required for rejection")
        updated_doc = await leaves_collection.find_one_and_update(
            {"leave_id": leave_id},
            {"$set": {
                "status": LeaveStatus.REJECTED,
                "rejection_reason": reason,
                "rejected_by": current_user.get("employee_id"),
                "rejected_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }},
            return_document=True
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")
    # Return updated pending list
    query = {"status": LeaveStatus.PENDING}
    leaves = await leaves_collection.find(query).sort("applied_on", -1).to_list(None)
    leave_list = [
        Leave(
            leave_id=leave["leave_id"],
            employee_id=leave["employee_id"],
            leave_type=leave["leave_type"],
            start_date=extract_date(leave["start_date"]),
            end_date=extract_date(leave["end_date"]),
            reason=leave["reason"],
            status=leave["status"],
            applied_on=leave["applied_on"]
        )
        for leave in leaves
    ]
    return PendingLeaveListResponse(
        message=f"Updated. {len(leave_list)} pending leave requests remain.",
        data=leave_list
    )

async def get_leaves_collection():
    """Get leaves collection from database"""
    return db.leaves


async def get_leave_balance_collection():
    """Get leave balance collection from database"""
    return db.leave_balances


class UserRoles:
    """User role checks"""
    ADMIN = "admin"
    MANAGER = "manager"
    HR = "hr"
    EMPLOYEE = "employee"


def extract_date(field_value):
    """Helper function to extract date from datetime, date, or string"""
    if isinstance(field_value, datetime):
        return field_value.date()
    elif isinstance(field_value, date):
        return field_value
    elif isinstance(field_value, str):
        return datetime.fromisoformat(field_value).date()
    return field_value


async def check_overlapping_leaves(
    employee_id: str,
    start_date: date,
    end_date: date,
    leave_id: Optional[str] = None
) -> bool:
    """Check if there are overlapping leave requests"""
    leaves_collection = await get_leaves_collection()
    
    # Convert date to datetime for MongoDB query
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    query = {
        "employee_id": employee_id,
        "status": {"$in": [LeaveStatus.PENDING, LeaveStatus.APPROVED]},
        "$or": [
            {
                "$and": [
                    {"start_date": {"$lte": end_datetime}},
                    {"end_date": {"$gte": start_datetime}}
                ]
            }
        ]
    }
    
    # Exclude current leave if updating
    if leave_id:
        query["_id"] = {"$ne": ObjectId(leave_id)}
    
    overlapping = await leaves_collection.find_one(query)
    return overlapping is not None


async def get_leave_balance(employee_id: str) -> Optional[dict]:
    """Get leave balance for an employee"""
    balance_collection = await get_leave_balance_collection()
    return await balance_collection.find_one({"employee_id": employee_id})


async def update_leave_balance(employee_id: str, leave_days: int):
    """Update leave balance when a leave is approved"""
    balance_collection = await get_leave_balance_collection()
    
    # Get current balance
    current = await balance_collection.find_one({"employee_id": employee_id})
    if not current:
        raise ValueError(f"Leave balance not found for {employee_id}")
    
    # Calculate new remaining leaves
    new_used = current.get("used_leaves", 0) + leave_days
    new_remaining = current.get("total_leaves", 0) - new_used
    
    # Update with calculated values
    await balance_collection.update_one(
        {"employee_id": employee_id},
        {
            "$set": {
                "used_leaves": new_used,
                "remaining_leaves": new_remaining
            }
        }
    )


@router.post("/apply", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def apply_leave(
    leave_create: LeaveCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Apply for a new leave request
    
    - Validate overlapping leaves with approved/pending leaves
    - Check if employee has sufficient leave balance
    - Save leave request with Pending status
    """
    employee_id = leave_create.employee_id
    
    # Verify employee exists in the system using centralized validator
    await validate_employee_exists(employee_id)
    
    # Verify employee can only apply for their own leaves
    if current_user.get("role") == UserRoles.EMPLOYEE:
        if current_user.get("employee_id") != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees can only apply leaves for themselves"
            )
    
    # Validate dates
    if leave_create.start_date > leave_create.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date cannot be after end date"
        )
    
    if leave_create.start_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot apply for past dates"
        )
    
    # Check for overlapping leaves
    has_overlap = await check_overlapping_leaves(
        employee_id,
        leave_create.start_date,
        leave_create.end_date
    )
    
    if has_overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Leave already exists for the selected dates"
        )
    
    # Check leave balance
    balance = await get_leave_balance(employee_id)
    
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave balance not found for employee"
        )
    
    leave_days = (leave_create.end_date - leave_create.start_date).days + 1
    
    if balance["remaining_leaves"] < leave_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient leave balance. Available: {balance['remaining_leaves']}, Requested: {leave_days}"
        )
    
    # Create leave request
    leaves_collection = await get_leaves_collection()
    
    # Convert dates to datetime for MongoDB storage
    start_datetime = datetime.combine(leave_create.start_date, datetime.min.time())
    end_datetime = datetime.combine(leave_create.end_date, datetime.max.time())
    
    leave_doc = {
        "_id": ObjectId(),
        "leave_id": str(uuid4()),
        "employee_id": employee_id,
        "leave_type": leave_create.leave_type,
        "start_date": start_datetime,
        "end_date": end_datetime,
        "reason": leave_create.reason,
        "status": LeaveStatus.PENDING,
        "applied_on": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await leaves_collection.insert_one(leave_doc)
    
    leave = Leave(
        leave_id=leave_doc["leave_id"],
        employee_id=leave_doc["employee_id"],
        leave_type=leave_doc["leave_type"],
        start_date=extract_date(leave_doc["start_date"]),
        end_date=extract_date(leave_doc["end_date"]),
        reason=leave_doc["reason"],
        status=leave_doc["status"],
        applied_on=leave_doc["applied_on"]
    )
    
    return LeaveResponse(
        message="Leave request submitted successfully",
        data=leave
    )


@router.get("/history/{employee_id}", response_model=dict)
async def get_leave_history(
    employee_id: str,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get leave history for an employee
    
    - Employees can only view their own history
    - Managers/HR/Admins can view any employee's history
    - Optional status_filter: Filter by status ('Pending', 'Approved', 'Rejected')
    """
    # Verify access
    if current_user.get("role") == UserRoles.EMPLOYEE:
        if current_user.get("employee_id") != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees can only view their own leave history"
            )
    
    leaves_collection = await get_leaves_collection()
    
    query = {"employee_id": employee_id}
    
    if status_filter:
        try:
            # Validate the status is valid, but use the string value for the query
            LeaveStatus(status_filter)
            query["status"] = status_filter
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join([s.value for s in LeaveStatus])}"
            )
    
    leaves = await leaves_collection.find(query).sort("applied_on", -1).to_list(None)
    
    leave_list = [
        Leave(
            leave_id=leave["leave_id"],
            employee_id=leave["employee_id"],
            leave_type=leave["leave_type"],
            start_date=extract_date(leave["start_date"]),
            end_date=extract_date(leave["end_date"]),
            reason=leave["reason"],
            status=leave["status"],
            applied_on=leave["applied_on"]
        )
        for leave in leaves
    ]
    
    return {
        "message": f"Found {len(leave_list)} leave records",
        "data": leave_list
    }


@router.post("/approve/{leave_id}", response_model=LeaveResponse)
async def approve_leave(
    leave_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Approve a leave request
    
    - Only Manager, HR, or Admin can approve leaves
    - Updates leave status to Approved
    - Updates employee's leave balance
    """
    # Role-based access control
    allowed_roles = [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN]
    if current_user.get("role", "").lower() not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Managers, HR, or Admins can approve leaves"
        )
    
    leaves_collection = await get_leaves_collection()
    
    # Find leave request
    leave_doc = await leaves_collection.find_one({"leave_id": leave_id})
    
    if not leave_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found"
        )
    
    if leave_doc["status"] != LeaveStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve Pending leaves. Current status: {leave_doc['status']}"
        )
    
    # Calculate leave days
    leave_days = (leave_doc["end_date"] - leave_doc["start_date"]).days + 1
    
    # Update leave status
    updated_doc = await leaves_collection.find_one_and_update(
        {"leave_id": leave_id},
        {
            "$set": {
                "status": LeaveStatus.APPROVED,
                "approved_by": current_user.get("employee_id"),
                "approved_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    
    # Update leave balance
    await update_leave_balance(leave_doc["employee_id"], leave_days)
    
    leave = Leave(
        leave_id=updated_doc["leave_id"],
        employee_id=updated_doc["employee_id"],
        leave_type=updated_doc["leave_type"],
        start_date=extract_date(updated_doc["start_date"]),
        end_date=extract_date(updated_doc["end_date"]),
        reason=updated_doc["reason"],
        status=updated_doc["status"],
        applied_on=updated_doc["applied_on"]
    )
    
    return LeaveResponse(
        message=f"Leave request approved successfully. {leave_days} days deducted from leave balance",
        data=leave
    )


@router.post("/reject/{leave_id}", response_model=LeaveResponse)
async def reject_leave(
    leave_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Reject a leave request
    
    - Only Manager, HR, or Admin can reject leaves
    - Updates leave status to Rejected
    - Leave balance remains unchanged
    """
    # Role-based access control
    allowed_roles = [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN]
    if current_user.get("role", "").lower() not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Managers, HR, or Admins can reject leaves"
        )
    
    leaves_collection = await get_leaves_collection()
    
    # Find leave request
    leave_doc = await leaves_collection.find_one({"leave_id": leave_id})
    
    if not leave_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found"
        )
    
    if leave_doc["status"] != LeaveStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only reject Pending leaves. Current status: {leave_doc['status']}"
        )
    
    # Update leave status
    updated_doc = await leaves_collection.find_one_and_update(
        {"leave_id": leave_id},
        {
            "$set": {
                "status": LeaveStatus.REJECTED,
                "rejection_reason": reason,
                "rejected_by": current_user.get("employee_id"),
                "rejected_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    
    leave = Leave(
        leave_id=updated_doc["leave_id"],
        employee_id=updated_doc["employee_id"],
        leave_type=updated_doc["leave_type"],
        start_date=extract_date(updated_doc["start_date"]),
        end_date=extract_date(updated_doc["end_date"]),
        reason=updated_doc["reason"],
        status=updated_doc["status"],
        applied_on=updated_doc["applied_on"]
    )
    
    return LeaveResponse(
        message="Leave request rejected successfully",
        data=leave
    )


@router.get("/balance/{employee_id}", response_model=LeaveBalanceResponse)
async def get_leave_balance_api(
    employee_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get leave balance for an employee
    
    - Employees can only view their own balance
    - Managers/HR/Admins can view any employee's balance
    """
    # Verify access
    if current_user.get("role") == UserRoles.EMPLOYEE:
        if current_user.get("employee_id") != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees can only view their own leave balance"
            )
    
    balance_doc = await get_leave_balance(employee_id)
    
    if not balance_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave balance not found for employee"
        )
    
    # Calculate remaining leaves (handle both old and new format)
    total = balance_doc.get("total_leaves", 0)
    used = balance_doc.get("used_leaves", 0)
    remaining = total - used
    
    balance = LeaveBalance(
        employee_id=balance_doc["employee_id"],
        total_leaves=total,
        used_leaves=used,
        remaining_leaves=remaining
    )
    
    return LeaveBalanceResponse(
        message="Leave balance retrieved successfully",
        data=balance
    )


@router.post("/balance/create", response_model=LeaveBalanceResponse, status_code=status.HTTP_201_CREATED)
async def create_leave_balance(
    balance_create: LeaveBalanceCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create initial leave balance for an employee
    
    - Only HR or Admin can create leave balance
    """
    # Role-based access control
    allowed_roles = [UserRoles.HR, UserRoles.ADMIN]
    if current_user.get("role", "").lower() not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR or Admin can create leave balance"
        )
    
    balance_collection = await get_leave_balance_collection()
    
    # Check if balance already exists
    existing = await balance_collection.find_one({"employee_id": balance_create.employee_id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Leave balance already exists for this employee"
        )
    
    balance_doc = {
        "_id": ObjectId(),
        "employee_id": balance_create.employee_id,
        "total_leaves": balance_create.total_leaves,
        "used_leaves": balance_create.used_leaves,
        "remaining_leaves": balance_create.total_leaves - balance_create.used_leaves,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await balance_collection.insert_one(balance_doc)
    
    balance = LeaveBalance(
        employee_id=balance_doc["employee_id"],
        total_leaves=balance_doc["total_leaves"],
        used_leaves=balance_doc["used_leaves"],
        remaining_leaves=balance_doc["remaining_leaves"]
    )
    
    return LeaveBalanceResponse(
        message="Leave balance created successfully",
        data=balance
    )

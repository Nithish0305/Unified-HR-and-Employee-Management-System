from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from datetime import datetime, date
from uuid import uuid4
from typing import List, Optional
from decimal import Decimal
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os

from .models import (
    Salary, SalaryCreate, SalaryUpdate, SalaryResponse, SalaryListResponse,
    Promotion, PromotionCreate, PromotionUpdate, PromotionResponse, PromotionListResponse,
    AuditLog, AuditLogCreate, AuditAction, SalaryStatus, PromotionStatus,
    EmployeeSalaryInfo, EmployeePromotionInfo
)

# This should be imported from your main app's dependencies
from dependencies import get_current_user
from database import db
from employee_validator import validate_employee_exists

router = APIRouter(tags=["salary and promotion"])


async def get_salaries_collection():
    """Get salaries collection from database"""
    return db.salaries


async def get_promotions_collection():
    """Get promotions collection from database"""
    return db.promotions


async def get_audit_logs_collection():
    """Get audit logs collection from database"""
    return db.audit_logs


class UserRoles:
    """User role constants"""
    ADMIN = "admin"
    HR = "hr"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class ApprovalLevel:
    """Approval level hierarchy"""
    LEVEL_1 = "manager"  # Manager approval
    LEVEL_2 = "hr"       # HR approval
    LEVEL_3 = "admin"    # Admin approval


async def log_audit(
    action: AuditAction,
    module: str,
    record_id: str,
    performed_by: str,
    changes: Optional[dict] = None,
    remarks: Optional[str] = None,
    status: str = "SUCCESS"
):
    """Log an action to audit log"""
    try:
        audit_collection = await get_audit_logs_collection()
        audit_doc = {
            "_id": ObjectId(),
            "audit_id": str(uuid4()),
            "action": action.value,
            "module": module,
            "record_id": record_id,
            "performed_by": performed_by,
            "timestamp": datetime.utcnow(),
            "changes": changes,
            "remarks": remarks,
            "status": status
        }
        await audit_collection.insert_one(audit_doc)
    except Exception as e:
        print(f"Error logging audit: {str(e)}")


async def check_role_access(
    current_user: dict,
    required_roles: List[str],
    error_message: str = "Insufficient permissions"
) -> bool:
    """Check if user has required role"""
    user_role = current_user.get("role", "").lower()
    if user_role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_message
        )
    return True


# ==================== SALARY ROUTES ====================

@router.post("/salary/initiate", response_model=SalaryResponse, status_code=status.HTTP_201_CREATED)
async def initiate_salary_change(
    salary_create: SalaryCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Initiate a salary change request
    
    - Only Managers, HR, and Admins can initiate salary changes
    - Validates salary is positive and greater than current
    - Creates salary request with Pending status
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can initiate salary changes"
    )
    
    # Verify employee exists in the system using centralized validator
    await validate_employee_exists(salary_create.employee_id)
    
    # Validate proposed salary
    if salary_create.proposed_salary <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposed salary must be greater than zero"
        )
    
    if salary_create.proposed_salary <= salary_create.current_salary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposed salary must be greater than current salary"
        )
    
    # Validate effective date
    if salary_create.effective_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Effective date cannot be in the past"
        )
    
    # Check for existing pending salary change
    salaries_collection = await get_salaries_collection()
    existing = await salaries_collection.find_one({
        "employee_id": salary_create.employee_id,
        "status": SalaryStatus.PENDING
    })
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee already has a pending salary change request"
        )
    
    # Calculate salary increase
    salary_increase = salary_create.proposed_salary - salary_create.current_salary
    increase_percentage = float((salary_increase / salary_create.current_salary) * 100)
    
    # Create salary document
    # Convert effective_date (date) to datetime for MongoDB BSON compatibility
    effective_date_dt = datetime.combine(salary_create.effective_date, datetime.min.time())
    salary_doc = {
        "_id": ObjectId(),
        "salary_id": str(uuid4()),
        "employee_id": salary_create.employee_id,
        "current_salary": float(salary_create.current_salary),
        "proposed_salary": float(salary_create.proposed_salary),
        "salary_increase": float(salary_increase),
        "increase_percentage": increase_percentage,
        "effective_date": effective_date_dt,
        "reason": salary_create.reason,
        "status": SalaryStatus.PENDING,
        "initiated_by": current_user.get("employee_id"),
        "approval_level": ApprovalLevel.LEVEL_1,  # Next approval from manager
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await salaries_collection.insert_one(salary_doc)
    
    # Log audit
    await log_audit(
        AuditAction.CREATE,
        "salary",
        salary_doc["salary_id"],
        current_user.get("employee_id"),
        changes={
            "current_salary": float(salary_create.current_salary),
            "proposed_salary": float(salary_create.proposed_salary)
        },
        remarks=salary_create.reason
    )
    
    salary = Salary(
        salary_id=salary_doc["salary_id"],
        employee_id=salary_doc["employee_id"],
        current_salary=Decimal(str(salary_doc["current_salary"])),
        proposed_salary=Decimal(str(salary_doc["proposed_salary"])),
        salary_increase=Decimal(str(salary_doc["salary_increase"])),
        increase_percentage=salary_doc["increase_percentage"],
        effective_date=salary_doc["effective_date"],
        reason=salary_doc["reason"],
        status=salary_doc["status"],
        initiated_by=salary_doc["initiated_by"],
        created_at=salary_doc["created_at"],
        updated_at=salary_doc["updated_at"]
    )
    
    return SalaryResponse(
        message="Salary change initiated successfully",
        data=salary
    )


@router.post("/salary/approve/{salary_id}", response_model=SalaryResponse)
async def approve_salary_change(
    salary_id: str,
    remarks: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Approve a salary change request
    
    - Multi-level approval: Manager → HR → Admin
    - Only authorized users can approve at their level
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can approve salary changes"
    )
    
    salaries_collection = await get_salaries_collection()
    
    # Find salary request
    salary_doc = await salaries_collection.find_one({"salary_id": salary_id})
    
    if not salary_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salary change request not found"
        )
    
    if salary_doc["status"] != SalaryStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve Pending requests. Current status: {salary_doc['status']}"
        )
    
    # Check approval level
    current_level = salary_doc.get("approval_level", ApprovalLevel.LEVEL_1)
    user_role = current_user.get("role", "").lower()
    
    # Validate user role matches required level
    if current_level == ApprovalLevel.LEVEL_1 and user_role not in [UserRoles.MANAGER, UserRoles.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin approval required at this level"
        )
    elif current_level == ApprovalLevel.LEVEL_2 and user_role not in [UserRoles.HR, UserRoles.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR or Admin approval required at this level"
        )
    
    # Determine next level or final approval
    if current_level == ApprovalLevel.LEVEL_1:
        next_level = ApprovalLevel.LEVEL_2
        status_value = SalaryStatus.PENDING
        approval_remarks = f"Approved by Manager. Next: HR Review"
    elif current_level == ApprovalLevel.LEVEL_2:
        next_level = ApprovalLevel.LEVEL_3
        status_value = SalaryStatus.PENDING
        approval_remarks = f"Approved by HR. Final: Admin Approval"
    else:  # LEVEL_3
        next_level = None
        status_value = SalaryStatus.APPROVED
        approval_remarks = f"Approved by Admin. Salary change approved."
    
    # Update salary request
    update_data = {
        "$set": {
            "status": status_value,
            "approval_level": next_level,
            "updated_at": datetime.utcnow()
        }
    }
    
    if next_level is None:
        # Final approval
        update_data["$set"]["approved_by"] = current_user.get("employee_id")
        update_data["$set"]["approved_on"] = datetime.utcnow()
        update_data["$set"]["approval_remarks"] = remarks or approval_remarks
    
    updated_doc = await salaries_collection.find_one_and_update(
        {"salary_id": salary_id},
        update_data,
        return_document=True
    )
    
    # Log audit
    await log_audit(
        AuditAction.APPROVE,
        "salary",
        salary_id,
        current_user.get("employee_id"),
        remarks=remarks or approval_remarks
    )
    
    salary = Salary(
        salary_id=updated_doc["salary_id"],
        employee_id=updated_doc["employee_id"],
        current_salary=Decimal(str(updated_doc["current_salary"])),
        proposed_salary=Decimal(str(updated_doc["proposed_salary"])),
        salary_increase=Decimal(str(updated_doc["salary_increase"])),
        increase_percentage=updated_doc["increase_percentage"],
        effective_date=updated_doc["effective_date"],
        reason=updated_doc.get("reason"),
        status=updated_doc["status"],
        initiated_by=updated_doc["initiated_by"],
        approved_by=updated_doc.get("approved_by"),
        approval_remarks=updated_doc.get("approval_remarks"),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"],
        approved_on=updated_doc.get("approved_on")
    )
    
    message = "Salary change approved. Pending next level approval" if next_level else "Salary change fully approved"
    
    return SalaryResponse(
        message=message,
        data=salary
    )


@router.post("/salary/reject/{salary_id}", response_model=SalaryResponse)
async def reject_salary_change(
    salary_id: str,
    remarks: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Reject a salary change request
    
    - Only Managers, HR, and Admins can reject
    - Employee can view rejection reason
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can reject salary changes"
    )
    
    salaries_collection = await get_salaries_collection()
    
    # Find salary request
    salary_doc = await salaries_collection.find_one({"salary_id": salary_id})
    
    if not salary_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salary change request not found"
        )
    
    if salary_doc["status"] != SalaryStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only reject Pending requests. Current status: {salary_doc['status']}"
        )
    
    # Update salary request
    updated_doc = await salaries_collection.find_one_and_update(
        {"salary_id": salary_id},
        {
            "$set": {
                "status": SalaryStatus.REJECTED,
                "rejected_by": current_user.get("employee_id"),
                "rejection_reason": remarks,
                "rejected_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    
    # Log audit
    await log_audit(
        AuditAction.REJECT,
        "salary",
        salary_id,
        current_user.get("employee_id"),
        remarks=remarks
    )
    
    salary = Salary(
        salary_id=updated_doc["salary_id"],
        employee_id=updated_doc["employee_id"],
        current_salary=Decimal(str(updated_doc["current_salary"])),
        proposed_salary=Decimal(str(updated_doc["proposed_salary"])),
        salary_increase=Decimal(str(updated_doc["salary_increase"])),
        increase_percentage=updated_doc["increase_percentage"],
        effective_date=updated_doc["effective_date"],
        reason=updated_doc.get("reason"),
        status=updated_doc["status"],
        initiated_by=updated_doc["initiated_by"],
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"]
    )
    
    return SalaryResponse(
        message="Salary change request rejected",
        data=salary
    )


@router.get("/salary/history/{employee_id}", response_model=SalaryListResponse)
async def get_salary_history(
    employee_id: str,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get salary change history for an employee
    
    - Employees can view their own history
    - Managers/HR/Admins can view any employee's history
    """
    # Verify access
    if current_user.get("role", "").lower() == UserRoles.EMPLOYEE:
        if current_user.get("employee_id") != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees can only view their own salary history"
            )
    
    salaries_collection = await get_salaries_collection()
    
    query = {"employee_id": employee_id}
    
    if status_filter:
        try:
            query["status"] = SalaryStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join([s.value for s in SalaryStatus])}"
            )
    
    salaries = await salaries_collection.find(query).sort("created_at", -1).to_list(None)
    
    salary_list = [
        Salary(
            salary_id=sal["salary_id"],
            employee_id=sal["employee_id"],
            current_salary=Decimal(str(sal["current_salary"])),
            proposed_salary=Decimal(str(sal["proposed_salary"])),
            salary_increase=Decimal(str(sal.get("salary_increase", 0))),
            increase_percentage=sal.get("increase_percentage"),
            effective_date=sal["effective_date"],
            reason=sal.get("reason"),
            status=sal["status"],
            initiated_by=sal["initiated_by"],
            approved_by=sal.get("approved_by"),
            approval_remarks=sal.get("approval_remarks"),
            created_at=sal["created_at"],
            updated_at=sal["updated_at"],
            approved_on=sal.get("approved_on")
        )
        for sal in salaries
    ]
    
    return SalaryListResponse(
        message=f"Found {len(salary_list)} salary change records",
        total=len(salary_list),
        data=salary_list
    )


# ==================== PROMOTION ROUTES ====================

@router.post("/promotion/initiate", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
async def initiate_promotion(
    promotion_create: PromotionCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Initiate a promotion request
    
    - Only Managers, HR, and Admins can initiate promotions
    - Creates promotion with Pending status
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can initiate promotions"
    )
    
    # Validate roles are not the same
    if promotion_create.old_role.lower() == promotion_create.new_role.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New role must be different from current role"
        )
    
    # Validate effective date
    if promotion_create.effective_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Effective date cannot be in the past"
        )
    
    # Check for existing pending promotion
    promotions_collection = await get_promotions_collection()
    existing = await promotions_collection.find_one({
        "employee_id": promotion_create.employee_id,
        "status": PromotionStatus.PENDING
    })
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee already has a pending promotion request"
        )
    
    # Create promotion document
    # Convert effective_date (date) to datetime for MongoDB BSON compatibility
    effective_date_dt = datetime.combine(promotion_create.effective_date, datetime.min.time())
    promotion_doc = {
        "_id": ObjectId(),
        "promotion_id": str(uuid4()),
        "employee_id": promotion_create.employee_id,
        "old_role": promotion_create.old_role,
        "new_role": promotion_create.new_role,
        "effective_date": effective_date_dt,
        "reason": promotion_create.reason,
        "status": PromotionStatus.PENDING,
        "initiated_by": current_user.get("employee_id"),
        "approval_level": ApprovalLevel.LEVEL_1,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await promotions_collection.insert_one(promotion_doc)
    
    # Log audit
    await log_audit(
        AuditAction.CREATE,
        "promotion",
        promotion_doc["promotion_id"],
        current_user.get("employee_id"),
        changes={
            "old_role": promotion_create.old_role,
            "new_role": promotion_create.new_role
        },
        remarks=promotion_create.reason
    )
    
    promotion = Promotion(
        promotion_id=promotion_doc["promotion_id"],
        employee_id=promotion_doc["employee_id"],
        old_role=promotion_doc["old_role"],
        new_role=promotion_doc["new_role"],
        effective_date=promotion_doc["effective_date"],
        reason=promotion_doc["reason"],
        status=promotion_doc["status"],
        initiated_by=promotion_doc["initiated_by"],
        created_at=promotion_doc["created_at"],
        updated_at=promotion_doc["updated_at"]
    )
    
    return PromotionResponse(
        message="Promotion initiated successfully",
        data=promotion
    )


@router.post("/promotion/approve/{promotion_id}", response_model=PromotionResponse)
async def approve_promotion(
    promotion_id: str,
    remarks: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Approve a promotion request
    
    - Multi-level approval: Manager → HR → Admin
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can approve promotions"
    )
    
    promotions_collection = await get_promotions_collection()
    
    # Find promotion request
    promotion_doc = await promotions_collection.find_one({"promotion_id": promotion_id})
    
    if not promotion_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion request not found"
        )
    
    if promotion_doc["status"] != PromotionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve Pending requests. Current status: {promotion_doc['status']}"
        )
    
    # Check approval level
    current_level = promotion_doc.get("approval_level", ApprovalLevel.LEVEL_1)
    user_role = current_user.get("role", "").lower()
    
    # Validate user role matches required level
    if current_level == ApprovalLevel.LEVEL_1 and user_role not in [UserRoles.MANAGER, UserRoles.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin approval required at this level"
        )
    elif current_level == ApprovalLevel.LEVEL_2 and user_role not in [UserRoles.HR, UserRoles.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR or Admin approval required at this level"
        )
    
    # Determine next level
    if current_level == ApprovalLevel.LEVEL_1:
        next_level = ApprovalLevel.LEVEL_2
        status_value = PromotionStatus.PENDING
    elif current_level == ApprovalLevel.LEVEL_2:
        next_level = ApprovalLevel.LEVEL_3
        status_value = PromotionStatus.PENDING
    else:  # LEVEL_3
        next_level = None
        status_value = PromotionStatus.APPROVED
    
    # Update promotion request
    update_data = {
        "$set": {
            "status": status_value,
            "approval_level": next_level,
            "updated_at": datetime.utcnow()
        }
    }
    
    if next_level is None:
        update_data["$set"]["approved_by"] = "admin"
        update_data["$set"]["approved_on"] = datetime.utcnow()
        update_data["$set"]["approval_remarks"] = remarks
        # Generate PDF and update promotion document
        from modules.salary.generate_promotion_pdf import generate_promotion_pdf
        pdf_path = generate_promotion_pdf(promotion_doc)
        update_data["$set"]["pdf_path"] = pdf_path
    
    updated_doc = await promotions_collection.find_one_and_update(
        {"promotion_id": promotion_id},
        update_data,
        return_document=True
    )
    
    # Log audit
    await log_audit(
        AuditAction.APPROVE,
        "promotion",
        promotion_id,
        current_user.get("employee_id"),
        remarks=remarks or f"Approved at {current_level} level"
    )
    
    promotion = Promotion(
        promotion_id=updated_doc["promotion_id"],
        employee_id=updated_doc["employee_id"],
        old_role=updated_doc["old_role"],
        new_role=updated_doc["new_role"],
        effective_date=updated_doc["effective_date"],
        reason=updated_doc.get("reason"),
        status=updated_doc["status"],
        initiated_by=updated_doc["initiated_by"],
        approved_by=updated_doc.get("approved_by"),
        approval_remarks=updated_doc.get("approval_remarks"),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"],
        approved_on=updated_doc.get("approved_on")
    )
    
    message = "Promotion approved. Pending next level approval" if next_level else "Fully approved, you are promoted"
    
    return PromotionResponse(
        message=message,
        data=promotion
    )


@router.post("/promotion/reject/{promotion_id}", response_model=PromotionResponse)
async def reject_promotion(
    promotion_id: str,
    remarks: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Reject a promotion request
    
    - Only Managers, HR, and Admins can reject
    """
    # Role-based access control
    await check_role_access(
        current_user,
        [UserRoles.MANAGER, UserRoles.HR, UserRoles.ADMIN],
        "Only Managers, HR, and Admins can reject promotions"
    )
    
    promotions_collection = await get_promotions_collection()
    
    # Find promotion request
    promotion_doc = await promotions_collection.find_one({"promotion_id": promotion_id})
    
    if not promotion_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion request not found"
        )
    
    if promotion_doc["status"] != PromotionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only reject Pending requests. Current status: {promotion_doc['status']}"
        )
    
    # Update promotion request
    updated_doc = await promotions_collection.find_one_and_update(
        {"promotion_id": promotion_id},
        {
            "$set": {
                "status": PromotionStatus.REJECTED,
                "rejected_by": current_user.get("employee_id"),
                "rejection_reason": remarks,
                "rejected_on": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    
    # Log audit
    await log_audit(
        AuditAction.REJECT,
        "promotion",
        promotion_id,
        current_user.get("employee_id"),
        remarks=remarks
    )
    
    promotion = Promotion(
        promotion_id=updated_doc["promotion_id"],
        employee_id=updated_doc["employee_id"],
        old_role=updated_doc["old_role"],
        new_role=updated_doc["new_role"],
        effective_date=updated_doc["effective_date"],
        reason=updated_doc.get("reason"),
        status=updated_doc["status"],
        initiated_by=updated_doc["initiated_by"],
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"]
    )
    
    return PromotionResponse(
        message="Promotion request rejected",
        data=promotion
    )


@router.get("/promotion/history/{employee_id}", response_model=PromotionListResponse)
async def get_promotion_history(
    employee_id: str,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get promotion history for an employee
    
    - Employees can view their own history
    - Managers/HR/Admins can view any employee's history
    """
    # Verify access
    if current_user.get("role", "").lower() == UserRoles.EMPLOYEE:
        if current_user.get("employee_id") != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees can only view their own promotion history"
            )
    
    promotions_collection = await get_promotions_collection()
    
    query = {"employee_id": employee_id}
    
    if status_filter:
        try:
            query["status"] = PromotionStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join([s.value for s in PromotionStatus])}"
            )
    
    promotions = await promotions_collection.find(query).sort("created_at", -1).to_list(None)
    
    promotion_list = [
        Promotion(
            promotion_id=promo["promotion_id"],
            employee_id=promo["employee_id"],
            old_role=promo["old_role"],
            new_role=promo["new_role"],
            effective_date=promo["effective_date"],
            reason=promo.get("reason"),
            status=promo["status"],
            initiated_by=promo["initiated_by"],
            approved_by=promo.get("approved_by"),
            approval_remarks=promo.get("approval_remarks"),
            created_at=promo["created_at"],
            updated_at=promo["updated_at"],
            approved_on=promo.get("approved_on")
        )
        for promo in promotions
    ]
    
    return PromotionListResponse(
        message=f"Found {len(promotion_list)} promotion records",
        total=len(promotion_list),
        data=promotion_list
    )

@router.get("/promotion/{promotion_id}/pdf")
async def get_promotion_pdf(
    promotion_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download promotion PDF document
    
    Path Parameters:
    - promotion_id: str (UUID of the promotion)
    
    RBAC:
    - Employees can only download their own promotion PDF
    - Managers, HR, and Admins can download any promotion PDF
    """
    try:
        promotions_collection = await get_promotions_collection()
        
        # Find promotion request
        promotion_doc = await promotions_collection.find_one({"promotion_id": promotion_id})
        
        if not promotion_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Promotion request not found"
            )
        
        # RBAC: Verify access control
        user_role = current_user.get("role", "").lower()
        if user_role == UserRoles.EMPLOYEE:
            if current_user.get("employee_id") != promotion_doc["employee_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employees can only view their own promotion PDF"
                )
        
        # Check if PDF path is stored in promotion document
        pdf_path = promotion_doc.get("pdf_path")
        
        if not pdf_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Promotion PDF not available. Please contact HR to generate the document."
            )
        
        # Verify the file actually exists
        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Promotion PDF file not found on server"
            )
        
        # Return the PDF file
        return FileResponse(
            path=pdf_path,
            filename=f"promotion_{promotion_id}.pdf",
            media_type="application/pdf"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
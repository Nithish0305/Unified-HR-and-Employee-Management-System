"""
Salary and Promotion Service
Provides business logic and helper functions for salary and promotion management
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from decimal import Decimal

from .models import SalaryStatus, PromotionStatus, AuditAction


class SalaryService:
    """Service class for salary management operations"""
    
    def __init__(self, db: AsyncIOMotorClient):
        """Initialize SalaryService with database connection"""
        self.db = db
        self.salaries_collection = db.get_collection("salaries")
        self.promotions_collection = db.get_collection("promotions")
        self.audit_logs_collection = db.get_collection("audit_logs")
        self.salary_history_collection = db.get_collection("salary_history")
    
    class ApprovalConfig:
        """Approval configuration"""
        LEVEL_1 = "manager"
        LEVEL_2 = "hr"
        LEVEL_3 = "admin"
        
        LEVELS = [LEVEL_1, LEVEL_2, LEVEL_3]
        
        ROLE_LEVEL_MAP = {
            "manager": [LEVEL_1],
            "hr": [LEVEL_2],
            "admin": [LEVEL_1, LEVEL_2, LEVEL_3]
        }
    
    # ==================== Salary Validation ====================
    
    async def validate_salary_update(
        self,
        employee_id: str,
        current_salary: Decimal,
        proposed_salary: Decimal,
        effective_date: date,
        allow_pending: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate salary update request
        
        Args:
            employee_id: Employee ID
            current_salary: Current salary amount
            proposed_salary: Proposed new salary
            effective_date: Effective date of change
            allow_pending: Whether to allow if pending request exists
        
        Returns:
            Tuple of (is_valid, error_message)
        
        Raises:
            HTTPException: If validation fails critically
        """
        try:
            # Validate salary amounts
            if current_salary <= 0:
                return False, "Current salary must be greater than zero"
            
            if proposed_salary <= 0:
                return False, "Proposed salary must be greater than zero"
            
            if proposed_salary <= current_salary:
                return False, "Proposed salary must be greater than current salary"
            
            # Validate effective date
            if effective_date < date.today():
                return False, "Effective date cannot be in the past"
            
            # Check salary increase limit (max 50% per request)
            increase_percentage = float((proposed_salary - current_salary) / current_salary * 100)
            if increase_percentage > 50:
                return False, "Salary increase cannot exceed 50% per request"
            
            # Check existing pending request
            existing_pending = await self.salaries_collection.find_one({
                "employee_id": employee_id,
                "status": SalaryStatus.PENDING
            })
            
            if existing_pending and not allow_pending:
                return False, "Employee already has a pending salary change request"
            
            # Check frequency of salary changes (max 2 per year)
            year_start = date(date.today().year, 1, 1)
            year_end = date(date.today().year, 12, 31)
            
            approved_this_year = await self.salaries_collection.count_documents({
                "employee_id": employee_id,
                "status": SalaryStatus.APPROVED,
                "effective_date": {
                    "$gte": year_start,
                    "$lte": year_end
                }
            })
            
            if approved_this_year >= 2:
                return False, "Maximum 2 salary changes allowed per year"
            
            return True, None
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error validating salary update: {str(e)}"
            )
    
    async def validate_salary_amount(
        self,
        employee_id: str,
        amount: Decimal
    ) -> bool:
        """
        Validate salary amount is reasonable
        
        Args:
            employee_id: Employee ID
            amount: Salary amount to validate
        
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check against company salary scales (if available)
            if amount < 0:
                return False
            
            # Very high salary check
            if amount > Decimal("10000000"):  # 10 million limit
                return False
            
            return True
        
        except Exception:
            return False
    
    # ==================== Multi-Level Approval ====================
    
    async def multi_level_approval_check(
        self,
        current_user: dict,
        request_id: str,
        request_type: str = "salary"
    ) -> Tuple[str, str, bool]:
        """
        Check user authorization for multi-level approval
        
        Args:
            current_user: Current user dictionary with 'role' and 'employee_id'
            request_id: Request ID (salary_id or promotion_id)
            request_type: Type of request ('salary' or 'promotion')
        
        Returns:
            Tuple of (current_level, next_level, is_authorized)
        
        Raises:
            HTTPException: If request not found or invalid
        """
        try:
            user_role = current_user.get("role", "").lower()
            user_id = current_user.get("employee_id")
            
            # Get request
            if request_type == "salary":
                collection = self.salaries_collection
                id_field = "salary_id"
            else:
                collection = self.promotions_collection
                id_field = "promotion_id"
            
            request_doc = await collection.find_one({id_field: request_id})
            
            if not request_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{request_type.capitalize()} request not found"
                )
            
            # Check if already approved
            if request_doc["status"] in [SalaryStatus.APPROVED, SalaryStatus.REJECTED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot modify {request_doc['status']} request"
                )
            
            # Get current approval level
            current_level = request_doc.get("approval_level", self.ApprovalConfig.LEVEL_1)
            
            # Validate user role has permission for this level
            authorized_levels = self.ApprovalConfig.ROLE_LEVEL_MAP.get(user_role, [])
            
            if current_level not in authorized_levels:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your role ({user_role}) cannot approve at {current_level} level"
                )
            
            # Determine next level
            level_index = self.ApprovalConfig.LEVELS.index(current_level)
            next_level = self.ApprovalConfig.LEVELS[level_index + 1] if level_index < len(self.ApprovalConfig.LEVELS) - 1 else None
            
            return current_level, next_level, True
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error checking approval authority: {str(e)}"
            )
    
    async def check_approval_authority(
        self,
        user_role: str,
        required_level: str
    ) -> bool:
        """
        Check if user has authority at specific approval level
        
        Args:
            user_role: User's role
            required_level: Required approval level
        
        Returns:
            True if authorized, False otherwise
        """
        authorized_levels = self.ApprovalConfig.ROLE_LEVEL_MAP.get(user_role.lower(), [])
        return required_level in authorized_levels
    
    # ==================== Audit Logging ====================
    
    async def log_audit_action(
        self,
        action: AuditAction,
        module: str,
        record_id: str,
        performed_by: str,
        changes: Optional[Dict] = None,
        remarks: Optional[str] = None,
        status: str = "SUCCESS",
        ip_address: Optional[str] = None
    ) -> str:
        """
        Log an action to audit log collection
        
        Args:
            action: Action type (CREATE, UPDATE, APPROVE, REJECT, DELETE)
            module: Module name (salary, promotion)
            record_id: ID of affected record
            performed_by: Employee ID of person who performed action
            changes: Dictionary of changes made
            remarks: Additional remarks
            status: Status of action (SUCCESS, FAILED)
            ip_address: IP address of performer
        
        Returns:
            Audit ID
        
        Raises:
            HTTPException: If logging fails
        """
        try:
            from uuid import uuid4
            
            audit_doc = {
                "_id": ObjectId(),
                "audit_id": str(uuid4()),
                "action": action.value if isinstance(action, AuditAction) else action,
                "module": module,
                "record_id": record_id,
                "performed_by": performed_by,
                "timestamp": datetime.utcnow(),
                "ip_address": ip_address,
                "changes": changes,
                "remarks": remarks,
                "status": status
            }
            
            result = await self.audit_logs_collection.insert_one(audit_doc)
            return audit_doc["audit_id"]
        
        except Exception as e:
            print(f"Warning: Failed to log audit action: {str(e)}")
            return None
    
    async def get_audit_logs(
        self,
        module: Optional[str] = None,
        record_id: Optional[str] = None,
        action: Optional[str] = None,
        performed_by: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get audit logs with optional filters
        
        Args:
            module: Filter by module
            record_id: Filter by record ID
            action: Filter by action type
            performed_by: Filter by performer
            limit: Maximum records to return
        
        Returns:
            List of audit log documents
        """
        try:
            query = {}
            
            if module:
                query["module"] = module
            if record_id:
                query["record_id"] = record_id
            if action:
                query["action"] = action
            if performed_by:
                query["performed_by"] = performed_by
            
            logs = await self.audit_logs_collection.find(query)\
                .sort("timestamp", -1)\
                .limit(limit)\
                .to_list(None)
            
            return logs
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching audit logs: {str(e)}"
            )
    
    # ==================== Salary History Management ====================
    
    async def update_salary_history(
        self,
        employee_id: str,
        old_salary: Decimal,
        new_salary: Decimal,
        effective_date: date,
        reason: Optional[str] = None,
        approved_by: Optional[str] = None
    ) -> Dict:
        """
        Update salary history when salary is approved
        
        Args:
            employee_id: Employee ID
            old_salary: Previous salary
            new_salary: New salary
            effective_date: Date change becomes effective
            reason: Reason for change
            approved_by: Employee ID who approved
        
        Returns:
            Salary history document
        
        Raises:
            HTTPException: If update fails
        """
        try:
            from uuid import uuid4
            
            history_doc = {
                "_id": ObjectId(),
                "entry_id": str(uuid4()),
                "employee_id": employee_id,
                "old_salary": float(old_salary),
                "new_salary": float(new_salary),
                "salary_increase": float(new_salary - old_salary),
                "increase_percentage": float((new_salary - old_salary) / old_salary * 100),
                "effective_date": effective_date,
                "reason": reason,
                "approved_by": approved_by,
                "created_at": datetime.utcnow()
            }
            
            result = await self.salary_history_collection.insert_one(history_doc)
            return history_doc
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating salary history: {str(e)}"
            )
    
    async def get_salary_history(
        self,
        employee_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get salary change history for an employee
        
        Args:
            employee_id: Employee ID
            limit: Maximum records to return
        
        Returns:
            List of salary history documents
        """
        try:
            history = await self.salary_history_collection.find(
                {"employee_id": employee_id}
            ).sort("created_at", -1).limit(limit).to_list(None)
            
            return history
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching salary history: {str(e)}"
            )
    
    async def get_current_salary(
        self,
        employee_id: str
    ) -> Optional[Decimal]:
        """
        Get current active salary for an employee
        
        Args:
            employee_id: Employee ID
        
        Returns:
            Current salary amount or None if not found
        """
        try:
            # Get most recent approved salary change with past effective date
            today = date.today()
            
            latest_change = await self.salary_history_collection.find_one(
                {
                    "employee_id": employee_id,
                    "effective_date": {"$lte": today}
                },
                sort=[("effective_date", -1)]
            )
            
            if latest_change:
                return Decimal(str(latest_change["new_salary"]))
            
            return None
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching current salary: {str(e)}"
            )
    
    # ==================== Salary Statistics ====================
    
    async def get_salary_statistics(
        self,
        employee_id: Optional[str] = None
    ) -> Dict:
        """
        Get salary statistics
        
        Args:
            employee_id: Optional employee ID for single employee stats
        
        Returns:
            Dictionary with salary statistics
        """
        try:
            match_query = {}
            if employee_id:
                match_query["employee_id"] = employee_id
            
            pipeline = [
                {"$match": match_query},
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1},
                        "total_increase": {"$sum": "$salary_increase"}
                    }
                }
            ]
            
            stats = await self.salaries_collection.aggregate(pipeline).to_list(None)
            
            # Format results
            result = {
                "pending": {"count": 0, "total_increase": 0},
                "approved": {"count": 0, "total_increase": 0},
                "rejected": {"count": 0, "total_increase": 0}
            }
            
            for stat in stats:
                status_key = stat["_id"].lower()
                result[status_key] = {
                    "count": stat["count"],
                    "total_increase": float(stat["total_increase"])
                }
            
            return result
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error calculating statistics: {str(e)}"
            )
    
    # ==================== Approval Workflow ====================
    
    async def process_approval(
        self,
        request_id: str,
        request_type: str,
        approved_by: str,
        remarks: Optional[str] = None
    ) -> Dict:
        """
        Process approval workflow for salary/promotion request
        
        Args:
            request_id: Request ID
            request_type: Type ('salary' or 'promotion')
            approved_by: Employee ID of approver
            remarks: Approval remarks
        
        Returns:
            Updated request document
        
        Raises:
            HTTPException: If processing fails
        """
        try:
            if request_type == "salary":
                collection = self.salaries_collection
                id_field = "salary_id"
                final_status = SalaryStatus.APPROVED
            else:
                collection = self.promotions_collection
                id_field = "promotion_id"
                final_status = PromotionStatus.APPROVED
            
            request_doc = await collection.find_one({id_field: request_id})
            
            if not request_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{request_type.capitalize()} request not found"
                )
            
            # Determine next approval level
            current_level = request_doc.get("approval_level", self.ApprovalConfig.LEVEL_1)
            level_index = self.ApprovalConfig.LEVELS.index(current_level)
            next_level = self.ApprovalConfig.LEVELS[level_index + 1] if level_index < len(self.ApprovalConfig.LEVELS) - 1 else None
            
            # Prepare update
            update_doc = {
                "$set": {
                    "approval_level": next_level,
                    "updated_at": datetime.utcnow()
                }
            }
            
            # If final approval, update status
            if next_level is None:
                update_doc["$set"]["status"] = final_status
                update_doc["$set"]["approved_by"] = approved_by
                update_doc["$set"]["approved_on"] = datetime.utcnow()
                update_doc["$set"]["approval_remarks"] = remarks
            
            updated = await collection.find_one_and_update(
                {id_field: request_id},
                update_doc,
                return_document=True
            )
            
            return updated
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing approval: {str(e)}"
            )
    
    # ==================== Promotion History ====================
    
    async def update_promotion_history(
        self,
        employee_id: str,
        old_role: str,
        new_role: str,
        effective_date: date,
        approved_by: Optional[str] = None
    ) -> Dict:
        """
        Update promotion history when promotion is approved
        
        Args:
            employee_id: Employee ID
            old_role: Previous role
            new_role: New role
            effective_date: Date promotion becomes effective
            approved_by: Employee ID who approved
        
        Returns:
            Promotion history document
        """
        try:
            from uuid import uuid4
            
            promotion_history_collection = self.db.get_collection("promotion_history")
            
            history_doc = {
                "_id": ObjectId(),
                "entry_id": str(uuid4()),
                "employee_id": employee_id,
                "old_role": old_role,
                "new_role": new_role,
                "effective_date": effective_date,
                "approved_by": approved_by,
                "created_at": datetime.utcnow()
            }
            
            result = await promotion_history_collection.insert_one(history_doc)
            return history_doc
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating promotion history: {str(e)}"
            )
    
    async def get_promotion_history(
        self,
        employee_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get promotion history for an employee
        
        Args:
            employee_id: Employee ID
            limit: Maximum records to return
        
        Returns:
            List of promotion history documents
        """
        try:
            promotion_history_collection = self.db.get_collection("promotion_history")
            
            history = await promotion_history_collection.find(
                {"employee_id": employee_id}
            ).sort("created_at", -1).limit(limit).to_list(None)
            
            return history
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching promotion history: {str(e)}"
            )

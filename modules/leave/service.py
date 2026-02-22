"""
Leave Management Service
Provides business logic and helper functions for leave management operations
"""

from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Tuple
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from .models import LeaveStatus


class LeaveService:
    """Service class for leave management operations"""
    
    def __init__(self, db: AsyncIOMotorClient):
        """Initialize LeaveService with database connection"""
        self.db = db
        self.leaves_collection = db.get_collection("leaves")
        self.balance_collection = db.get_collection("leave_balances")
        self.policy_collection = db.get_collection("leave_policies")
    
    class LeavePolicy:
        """Leave policy constants"""
        MAX_CONSECUTIVE_DAYS = 30
        MAX_PER_YEAR = 20
        MIN_NOTICE_DAYS = 1  # Notice period in days
        LEAVE_YEAR_START_MONTH = 1  # January
        LEAVE_YEAR_START_DAY = 1
    
    # ==================== Overlapping Leave Checks ====================
    
    async def check_overlapping_leave(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        exclude_leave_id: Optional[str] = None,
        exclude_statuses: Optional[List[str]] = None
    ) -> bool:
        """
        Check if employee has overlapping leave requests
        
        Args:
            employee_id: Employee ID
            start_date: Leave start date
            end_date: Leave end date
            exclude_leave_id: Leave ID to exclude from check (for updates)
            exclude_statuses: Leave statuses to exclude from overlap check
        
        Returns:
            True if overlap exists, False otherwise
        
        Raises:
            HTTPException: If database query fails
        """
        try:
            if exclude_statuses is None:
                exclude_statuses = []
            
            # Statuses to check for overlap (default: Pending and Approved)
            statuses_to_check = [
                status for status in [LeaveStatus.PENDING, LeaveStatus.APPROVED]
                if status not in exclude_statuses
            ]
            
            query = {
                "employee_id": employee_id,
                "status": {"$in": statuses_to_check},
                "$or": [
                    {
                        "$and": [
                            {"start_date": {"$lte": end_date}},
                            {"end_date": {"$gte": start_date}}
                        ]
                    }
                ]
            }
            
            # Exclude the current leave if updating
            if exclude_leave_id:
                query["leave_id"] = {"$ne": exclude_leave_id}
            
            overlapping = await self.leaves_collection.find_one(query)
            return overlapping is not None
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error checking overlapping leaves: {str(e)}"
            )
    
    async def get_overlapping_leaves(
        self,
        employee_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """
        Get all overlapping leave requests for an employee
        
        Args:
            employee_id: Employee ID
            start_date: Leave start date
            end_date: Leave end date
        
        Returns:
            List of overlapping leave documents
        """
        try:
            query = {
                "employee_id": employee_id,
                "status": {"$in": [LeaveStatus.PENDING, LeaveStatus.APPROVED]},
                "$or": [
                    {
                        "$and": [
                            {"start_date": {"$lte": end_date}},
                            {"end_date": {"$gte": start_date}}
                        ]
                    }
                ]
            }
            
            leaves = await self.leaves_collection.find(query).to_list(None)
            return leaves
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching overlapping leaves: {str(e)}"
            )
    
    # ==================== Leave Balance Calculations ====================
    
    async def calculate_leave_balance(
        self,
        employee_id: str
    ) -> Dict[str, int]:
        """
        Calculate current leave balance for an employee
        
        Args:
            employee_id: Employee ID
        
        Returns:
            Dictionary with total_leaves, used_leaves, remaining_leaves
        
        Raises:
            HTTPException: If employee not found or database error
        """
        try:
            balance_doc = await self.balance_collection.find_one(
                {"employee_id": employee_id}
            )
            
            if not balance_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Leave balance not found for employee {employee_id}"
                )
            
            total_leaves = balance_doc.get("total_leaves", 0)
            used_leaves = balance_doc.get("used_leaves", 0)
            remaining_leaves = total_leaves - used_leaves
            
            return {
                "total_leaves": total_leaves,
                "used_leaves": used_leaves,
                "remaining_leaves": max(0, remaining_leaves)
            }
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error calculating leave balance: {str(e)}"
            )
    
    async def calculate_leave_days(
        self,
        start_date: date,
        end_date: date,
        exclude_weekends: bool = True
    ) -> int:
        """
        Calculate number of leave days between two dates
        
        Args:
            start_date: Leave start date
            end_date: Leave end date
            exclude_weekends: Whether to exclude Saturday and Sunday
        
        Returns:
            Number of leave days
        
        Raises:
            HTTPException: If dates are invalid
        """
        try:
            if start_date > end_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Start date cannot be after end date"
                )
            
            if exclude_weekends:
                # Count business days only (Monday=0, Sunday=6)
                leave_days = 0
                current_date = start_date
                
                while current_date <= end_date:
                    if current_date.weekday() < 5:  # Monday to Friday
                        leave_days += 1
                    current_date += timedelta(days=1)
                
                return leave_days
            else:
                # Calculate total days
                return (end_date - start_date).days + 1
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error calculating leave days: {str(e)}"
            )
    
    # ==================== Leave Balance Updates ====================
    
    async def update_leave_balance(
        self,
        employee_id: str,
        leave_days: int,
        operation: str = "deduct"
    ) -> Dict:
        """
        Update employee's leave balance
        
        Args:
            employee_id: Employee ID
            leave_days: Number of days to deduct or add
            operation: "deduct" to reduce balance, "refund" to add back
        
        Returns:
            Updated balance document
        
        Raises:
            HTTPException: If update fails
        """
        try:
            if operation == "deduct":
                update_doc = {
                    "$inc": {
                        "used_leaves": leave_days,
                        "remaining_leaves": -leave_days
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            elif operation == "refund":
                update_doc = {
                    "$inc": {
                        "used_leaves": -leave_days,
                        "remaining_leaves": leave_days
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid operation. Use 'deduct' or 'refund'"
                )
            
            updated_balance = await self.balance_collection.find_one_and_update(
                {"employee_id": employee_id},
                update_doc,
                return_document=True
            )
            
            if not updated_balance:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Leave balance not found for employee {employee_id}"
                )
            
            return updated_balance
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating leave balance: {str(e)}"
            )
    
    async def refund_leave_balance(
        self,
        employee_id: str,
        leave_days: int
    ) -> Dict:
        """
        Refund leave days (when a leave is rejected/cancelled)
        
        Args:
            employee_id: Employee ID
            leave_days: Number of days to refund
        
        Returns:
            Updated balance document
        """
        return await self.update_leave_balance(
            employee_id,
            leave_days,
            operation="refund"
        )
    
    # ==================== Leave Policy Validation ====================
    
    async def validate_leave_policy(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        leave_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate leave request against company leave policy
        
        Args:
            employee_id: Employee ID
            start_date: Leave start date
            end_date: Leave end date
            leave_type: Type of leave (e.g., Casual, Sick, Personal)
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Validate minimum notice period
            notice_days = (start_date - date.today()).days
            if notice_days < self.LeavePolicy.MIN_NOTICE_DAYS:
                return False, f"Minimum {self.LeavePolicy.MIN_NOTICE_DAYS} day(s) notice required. Apply at least 1 day in advance."
            
            # Calculate leave duration
            leave_days = await self.calculate_leave_days(start_date, end_date)
            
            # Validate consecutive days limit
            if leave_days > self.LeavePolicy.MAX_CONSECUTIVE_DAYS:
                return False, f"Cannot apply for more than {self.LeavePolicy.MAX_CONSECUTIVE_DAYS} consecutive days"
            
            # Check annual leave limit
            is_within_annual = await self._check_annual_leave_limit(
                employee_id,
                leave_days,
                start_date
            )
            if not is_within_annual:
                return False, f"Exceeds maximum {self.LeavePolicy.MAX_PER_YEAR} leaves per year"
            
            # Check leave type specific policies
            policy_valid, policy_error = await self._validate_leave_type_policy(
                employee_id,
                leave_type,
                start_date,
                end_date
            )
            if not policy_valid:
                return False, policy_error
            
            return True, None
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error validating leave policy: {str(e)}"
            )
    
    async def _check_annual_leave_limit(
        self,
        employee_id: str,
        leave_days: int,
        start_date: date
    ) -> bool:
        """Check if leave request exceeds annual leave limit"""
        try:
            # Calculate leave year start and end
            today = date.today()
            leave_year_start = date(
                today.year if today.month >= self.LeavePolicy.LEAVE_YEAR_START_MONTH else today.year - 1,
                self.LeavePolicy.LEAVE_YEAR_START_MONTH,
                self.LeavePolicy.LEAVE_YEAR_START_DAY
            )
            leave_year_end = date(
                leave_year_start.year + 1,
                self.LeavePolicy.LEAVE_YEAR_START_MONTH,
                self.LeavePolicy.LEAVE_YEAR_START_DAY - 1
            )
            
            # Get approved leaves in current year
            approved_leaves = await self.leaves_collection.find({
                "employee_id": employee_id,
                "status": LeaveStatus.APPROVED,
                "start_date": {"$gte": leave_year_start},
                "end_date": {"$lte": leave_year_end}
            }).to_list(None)
            
            total_used = sum(
                (leave["end_date"] - leave["start_date"]).days + 1
                for leave in approved_leaves
            )
            
            return (total_used + leave_days) <= self.LeavePolicy.MAX_PER_YEAR
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error checking annual leave limit: {str(e)}"
            )
    
    async def _validate_leave_type_policy(
        self,
        employee_id: str,
        leave_type: str,
        start_date: date,
        end_date: date
    ) -> Tuple[bool, Optional[str]]:
        """Validate leave type specific policies"""
        try:
            policy = await self.policy_collection.find_one(
                {"leave_type": leave_type}
            )
            
            if not policy:
                # If no specific policy found, allow the leave
                return True, None
            
            # Check maximum days per leave
            max_days = policy.get("max_consecutive_days")
            if max_days:
                leave_days = (end_date - start_date).days + 1
                if leave_days > max_days:
                    return False, f"{leave_type} leave cannot exceed {max_days} days"
            
            # Check requiring medical certificate for sick leave
            if leave_type.lower() == "sick":
                leave_days = (end_date - start_date).days + 1
                certificate_required_after = policy.get("certificate_required_after_days", 3)
                if leave_days > certificate_required_after:
                    # Note: In real implementation, check for certificate in leave request
                    pass
            
            return True, None
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error validating leave type policy: {str(e)}"
            )
    
    # ==================== Leave Status Updates ====================
    
    async def approve_leave(
        self,
        leave_id: str,
        approved_by: str
    ) -> Dict:
        """
        Approve a leave request and update balance
        
        Args:
            leave_id: Leave request ID
            approved_by: Employee ID of approver
        
        Returns:
            Updated leave document
        
        Raises:
            HTTPException: If leave not found or invalid status
        """
        try:
            leave = await self.leaves_collection.find_one({"leave_id": leave_id})
            
            if not leave:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Leave request not found"
                )
            
            if leave["status"] != LeaveStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot approve {leave['status']} leave. Only Pending leaves can be approved."
                )
            
            # Calculate leave days
            leave_days = (leave["end_date"] - leave["start_date"]).days + 1
            
            # Update leave status
            updated_leave = await self.leaves_collection.find_one_and_update(
                {"leave_id": leave_id},
                {
                    "$set": {
                        "status": LeaveStatus.APPROVED,
                        "approved_by": approved_by,
                        "approved_on": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            # Update leave balance
            await self.update_leave_balance(
                leave["employee_id"],
                leave_days,
                operation="deduct"
            )
            
            return updated_leave
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error approving leave: {str(e)}"
            )
    
    async def reject_leave(
        self,
        leave_id: str,
        rejected_by: str,
        reason: Optional[str] = None
    ) -> Dict:
        """
        Reject a leave request
        
        Args:
            leave_id: Leave request ID
            rejected_by: Employee ID of rejector
            reason: Rejection reason
        
        Returns:
            Updated leave document
        
        Raises:
            HTTPException: If leave not found or invalid status
        """
        try:
            leave = await self.leaves_collection.find_one({"leave_id": leave_id})
            
            if not leave:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Leave request not found"
                )
            
            if leave["status"] != LeaveStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reject {leave['status']} leave. Only Pending leaves can be rejected."
                )
            
            # Update leave status (no balance change)
            updated_leave = await self.leaves_collection.find_one_and_update(
                {"leave_id": leave_id},
                {
                    "$set": {
                        "status": LeaveStatus.REJECTED,
                        "rejected_by": rejected_by,
                        "rejection_reason": reason,
                        "rejected_on": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            return updated_leave
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error rejecting leave: {str(e)}"
            )
    
    async def cancel_leave(
        self,
        leave_id: str,
        cancelled_by: str,
        reason: Optional[str] = None
    ) -> Dict:
        """
        Cancel an approved leave and refund days
        
        Args:
            leave_id: Leave request ID
            cancelled_by: Employee ID of canceller
            reason: Cancellation reason
        
        Returns:
            Updated leave document
        
        Raises:
            HTTPException: If leave not found or not approved
        """
        try:
            leave = await self.leaves_collection.find_one({"leave_id": leave_id})
            
            if not leave:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Leave request not found"
                )
            
            if leave["status"] != LeaveStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Can only cancel Approved leaves. Current status: {leave['status']}"
                )
            
            # Calculate leave days to refund
            leave_days = (leave["end_date"] - leave["start_date"]).days + 1
            
            # Refund leave balance
            await self.refund_leave_balance(leave["employee_id"], leave_days)
            
            # Update leave status
            updated_leave = await self.leaves_collection.find_one_and_update(
                {"leave_id": leave_id},
                {
                    "$set": {
                        "status": "Cancelled",
                        "cancelled_by": cancelled_by,
                        "cancellation_reason": reason,
                        "cancelled_on": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            return updated_leave
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error cancelling leave: {str(e)}"
            )
    
    # ==================== Statistics & Reports ====================
    
    async def get_employee_leave_stats(
        self,
        employee_id: str,
        year: Optional[int] = None
    ) -> Dict:
        """
        Get leave statistics for an employee
        
        Args:
            employee_id: Employee ID
            year: Year to get stats for (default: current year)
        
        Returns:
            Dictionary with leave statistics
        """
        try:
            if year is None:
                year = date.today().year
            
            # Calculate date range
            year_start = date(year, self.LeavePolicy.LEAVE_YEAR_START_MONTH, self.LeavePolicy.LEAVE_YEAR_START_DAY)
            year_end = date(year + 1, self.LeavePolicy.LEAVE_YEAR_START_MONTH, self.LeavePolicy.LEAVE_YEAR_START_DAY - 1)
            
            # Aggregate pipeline
            pipeline = [
                {
                    "$match": {
                        "employee_id": employee_id,
                        "start_date": {"$gte": year_start},
                        "end_date": {"$lte": year_end}
                    }
                },
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1},
                        "total_days": {
                            "$sum": {
                                "$add": [
                                    {"$subtract": ["$end_date", "$start_date"]},
                                    1
                                ]
                            }
                        }
                    }
                }
            ]
            
            stats = await self.leaves_collection.aggregate(pipeline).to_list(None)
            
            # Format response
            response = {
                "employee_id": employee_id,
                "year": year,
                "pending": {"count": 0, "days": 0},
                "approved": {"count": 0, "days": 0},
                "rejected": {"count": 0, "days": 0}
            }
            
            for stat in stats:
                status_key = stat["_id"].lower()
                response[status_key] = {
                    "count": stat["count"],
                    "days": stat["total_days"]
                }
            
            return response
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching leave statistics: {str(e)}"
            )

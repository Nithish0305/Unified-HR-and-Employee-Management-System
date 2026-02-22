from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

class EmployeeRole(str, Enum):
    ADMIN = "Admin"
    HR = "HR"
    MANAGER = "Manager"
    EMPLOYEE = "Employee"

class EmployeeStatus(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

def prepare_employee_document(
    employee_id: str,
    name: str,
    email: str,
    role: str,
    department: str,
    salary: float,
    status: str = EmployeeStatus.ACTIVE,
    joining_date: datetime = None,
    promotion_history: Optional[List[Dict]] = None,
    manager_id: Optional[str] = None,
    created_at: datetime = None,
    updated_at: datetime = None
) -> dict:
    """
    Prepare an employee document for MongoDB insertion.
    """
    now = datetime.utcnow()
    employee_doc = {
        "employee_id": employee_id,
        "name": name,
        "email": email,
        "role": role,
        "department": department,
        "salary": salary,
        "status": status,
        "joining_date": joining_date or now,
        "promotion_history": promotion_history or [],
        "manager_id": manager_id,
        "created_at": created_at or now,
        "updated_at": updated_at or now
    }
    return employee_doc

"""
Centralized employee validation for all modules.
Ensures all modules access employees through the same interface.
"""
from fastapi import HTTPException, status
from database import db

async def validate_employee_exists(employee_id: str):
    """
    Validate that an employee exists in the system.
    Raises HTTPException if not found.
    """
    employee = await db.employees.find_one({"employee_id": employee_id})
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID '{employee_id}' not found in the system"
        )
    return employee

async def get_employee_by_id(employee_id: str):
    """
    Get employee details by employee_id.
    Returns None if not found.
    """
    return await db.employees.find_one({"employee_id": employee_id})

async def validate_employees_exist(employee_ids: list):
    """
    Validate that multiple employees exist in the system.
    Returns list of employees or raises HTTPException.
    """
    employees = []
    for emp_id in employee_ids:
        employee = await get_employee_by_id(emp_id)
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee with ID '{emp_id}' not found in the system"
            )
        employees.append(employee)
    return employees

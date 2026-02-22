from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from bson import ObjectId
from .schemas import EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeeCreateResponse
from .service import (
	create_employee, update_employee, activate_employee, deactivate_employee,
	delete_employee, get_all_employees, total_employees, active_employees,
	department_wise_count, role_wise_count
)
from .models import EmployeeRole

# Placeholder for dependency
from dependencies import get_current_user
# Placeholder for db
from database import db

router = APIRouter(prefix="/employees", tags=["Employee Management"])

def check_role(user, allowed_roles):
	if user["role"].lower() not in [role.lower() for role in allowed_roles]:
		raise HTTPException(status_code=403, detail="Not authorized.")

@router.post("", response_model=EmployeeCreateResponse)
async def create_employee_endpoint(employee: EmployeeCreate, current_user: dict = Depends(get_current_user)):
	check_role(current_user, [EmployeeRole.ADMIN, EmployeeRole.HR])
	emp_id, err = await create_employee(db, employee.dict())
	if err:
		raise HTTPException(status_code=400, detail=err)
	emp = await db.employees.find_one({"_id": ObjectId(emp_id)})
	if not emp:
		raise HTTPException(status_code=404, detail="Employee not found after creation")
	
	# Generate credentials for response
	username = employee.employee_id.lower()
	password = employee.employee_id  # Default password is the employee_id
	
	return EmployeeCreateResponse(
		id=str(emp["_id"]),
		employee_id=emp["employee_id"],
		name=emp["name"],
		email=emp["email"],
		role=emp["role"],
		department=emp["department"],
		salary=emp["salary"],
		status=emp.get("status") or "Active",  # Default to "Active" if None
		joining_date=str(emp.get("joining_date", "")),
		promotion_history=emp.get("promotion_history", []),
		manager_id=emp.get("manager_id"),
		created_at=str(emp.get("created_at", "")),
		updated_at=str(emp.get("updated_at", "")),
		username=username,
		password=password
	)

@router.get("", response_model=List[EmployeeResponse])
async def get_employees(skip: int = 0, limit: int = 20, current_user: dict = Depends(get_current_user)):
	employees = await get_all_employees(db, pagination={"skip": skip, "limit": limit})
	return [
		EmployeeResponse(
			id=str(emp["_id"]),
			employee_id=emp.get("employee_id", ""),
			name=emp.get("name", ""),
			email=emp.get("email", ""),
			role=emp.get("role", ""),
			department=emp.get("department", ""),
			salary=emp.get("salary", 0),
			status=emp.get("status") or "Active",
			joining_date=str(emp.get("joining_date", "")),
			promotion_history=emp.get("promotion_history", []),
			manager_id=emp.get("manager_id"),
			created_at=str(emp.get("created_at", "")),
			updated_at=str(emp.get("updated_at", ""))
		) for emp in employees
	]

@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
	emp = await db.employees.find_one({"employee_id": employee_id})
	if not emp:
		raise HTTPException(status_code=404, detail="Employee not found.")
	return EmployeeResponse(
		id=str(emp["_id"]),
		employee_id=emp.get("employee_id", ""),
		name=emp.get("name", ""),
		email=emp.get("email", ""),
		role=emp.get("role", ""),
		department=emp.get("department", ""),
		salary=emp.get("salary", 0),
		status=emp.get("status") or "Active",
		joining_date=str(emp.get("joining_date", "")),
		promotion_history=emp.get("promotion_history", []),
		manager_id=emp.get("manager_id"),
		created_at=str(emp.get("created_at", "")),
		updated_at=str(emp.get("updated_at", ""))
	)

@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee_endpoint(employee_id: str, employee: EmployeeUpdate, current_user: dict = Depends(get_current_user)):
	# Only HR/Admin can update salary
	if employee.salary is not None:
		check_role(current_user, [EmployeeRole.ADMIN, EmployeeRole.HR])
	result, err = await update_employee(db, employee_id, employee.dict(exclude_unset=True))
	if err:
		raise HTTPException(status_code=400, detail=err)
	if not result:
		raise HTTPException(status_code=404, detail="Employee not found or not updated.")
	emp = await db.employees.find_one({"employee_id": employee_id})
	return EmployeeResponse(
		id=str(emp["_id"]),
		employee_id=emp.get("employee_id", ""),
		name=emp.get("name", ""),
		email=emp.get("email", ""),
		role=emp.get("role", ""),
		department=emp.get("department", ""),
		salary=emp.get("salary", 0),
		status=emp.get("status") or "Active",
		joining_date=str(emp.get("joining_date", "")),
		promotion_history=emp.get("promotion_history", []),
		manager_id=emp.get("manager_id"),
		created_at=str(emp.get("created_at", "")),
		updated_at=str(emp.get("updated_at", ""))
	)

@router.patch("/{employee_id}/activate")
async def activate_employee_endpoint(employee_id: str, current_user: dict = Depends(get_current_user)):
	result = await activate_employee(db, employee_id)
	if not result:
		raise HTTPException(status_code=404, detail="Employee not found or not activated.")
	return {"message": "Employee activated."}

@router.patch("/{employee_id}/deactivate")
async def deactivate_employee_endpoint(employee_id: str, current_user: dict = Depends(get_current_user)):
	result = await deactivate_employee(db, employee_id)
	if not result:
		raise HTTPException(status_code=404, detail="Employee not found or not deactivated.")
	return {"message": "Employee deactivated."}

@router.delete("/{employee_id}")
async def delete_employee_endpoint(employee_id: str, current_user: dict = Depends(get_current_user)):
	check_role(current_user, [EmployeeRole.ADMIN, EmployeeRole.HR])
	result = await delete_employee(db, employee_id)
	if not result:
		raise HTTPException(status_code=404, detail="Employee not found or not deleted.")
	return {"message": "Employee deleted."}

# Dashboard endpoints
@router.get("/dashboard/summary")
async def dashboard_summary(current_user: dict = Depends(get_current_user)):
	return {
		"total_employees": await total_employees(db),
		"active_employees": await active_employees(db)
	}

@router.get("/dashboard/department-wise")
async def dashboard_department_wise(current_user: dict = Depends(get_current_user)):
	return {"department_counts": await department_wise_count(db)}

@router.get("/dashboard/role-wise")
async def dashboard_role_wise(current_user: dict = Depends(get_current_user)):
	return {"role_counts": await role_wise_count(db)}

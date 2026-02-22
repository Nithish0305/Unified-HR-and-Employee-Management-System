from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List, Dict
from .models import EmployeeRole

class EmployeeCreate(BaseModel):
	employee_id: str = Field(..., description="Custom Employee ID")
	name: str = Field(..., description="Employee name")
	email: EmailStr = Field(..., description="Employee email")
	role: str = Field(..., description="Employee role")
	department: str = Field(..., description="Department name")
	salary: float = Field(..., description="Salary amount")
	status: Optional[str] = Field(None, description="Employee status")
	joining_date: Optional[str] = Field(None, description="Joining date")
	promotion_history: Optional[List[Dict]] = Field(None, description="Promotion history")
	manager_id: Optional[str] = Field(None, description="Manager ID")
	created_at: Optional[str] = Field(None, description="Created at")
	updated_at: Optional[str] = Field(None, description="Updated at")

	@validator("salary")
	def salary_non_negative(cls, v):
		if v < 0:
			raise ValueError("Salary must be non-negative.")
		return v

	@validator("role")
	def valid_role(cls, v):
		valid_roles = [r.value for r in EmployeeRole]
		if v not in valid_roles:
			raise ValueError(f"Role must be one of: {', '.join(valid_roles)}")
		return v

	@validator("department")
	def department_not_empty(cls, v):
		if not v or not v.strip():
			raise ValueError("Department cannot be empty.")
		return v

class EmployeeUpdate(BaseModel):
	employee_id: Optional[str] = Field(None, description="Custom Employee ID")
	name: Optional[str] = Field(None, description="Employee name")
	email: Optional[EmailStr] = Field(None, description="Employee email")
	role: Optional[str] = Field(None, description="Employee role")
	department: Optional[str] = Field(None, description="Department name")
	salary: Optional[float] = Field(None, description="Salary amount")

	@validator("salary")
	def salary_non_negative(cls, v):
		if v is not None and v < 0:
			raise ValueError("Salary must be non-negative.")
		return v

	@validator("role")
	def valid_role(cls, v):
		if v is not None:
			valid_roles = [r.value for r in EmployeeRole]
			if v not in valid_roles:
				raise ValueError(f"Role must be one of: {', '.join(valid_roles)}")
		return v

	@validator("department")
	def department_not_empty(cls, v):
		if v is not None and not v.strip():
			raise ValueError("Department cannot be empty.")
		return v

class EmployeeResponse(BaseModel):
	id: str = Field(..., description="MongoDB Object ID")
	employee_id: str = Field(..., description="Custom Employee ID")
	name: str = Field(..., description="Employee name")
	email: EmailStr = Field(..., description="Employee email")
	role: str = Field(..., description="Employee role")
	department: str = Field(..., description="Department name")
	salary: float = Field(..., description="Salary amount")
	status: str = Field(..., description="Employee status")
	joining_date: Optional[str] = Field(None, description="Joining date")
	promotion_history: Optional[List[Dict]] = Field(None, description="Promotion history")
	manager_id: Optional[str] = Field(None, description="Manager ID")
	created_at: Optional[str] = Field(None, description="Created at")
	updated_at: Optional[str] = Field(None, description="Updated at")

class EmployeeCreateResponse(BaseModel):
	id: str = Field(..., description="MongoDB Object ID")
	employee_id: str = Field(..., description="Custom Employee ID")
	name: str = Field(..., description="Employee name")
	email: EmailStr = Field(..., description="Employee email")
	role: str = Field(..., description="Employee role")
	department: str = Field(..., description="Department name")
	salary: float = Field(..., description="Salary amount")
	status: str = Field(..., description="Employee status")
	joining_date: Optional[str] = Field(None, description="Joining date")
	promotion_history: Optional[List[Dict]] = Field(None, description="Promotion history")
	manager_id: Optional[str] = Field(None, description="Manager ID")
	created_at: Optional[str] = Field(None, description="Created at")
	updated_at: Optional[str] = Field(None, description="Updated at")
	username: str = Field(..., description="Username for login")
	password: str = Field(..., description="Temporary password (change after first login)")

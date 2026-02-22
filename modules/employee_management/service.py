from datetime import datetime
from bson import ObjectId
from .models import EmployeeStatus, prepare_employee_document
from security import hash_password

async def create_employee(db, data: dict):
    # Email uniqueness check
    existing_email = await db.employees.find_one({"email": data["email"]})
    if existing_email:
        return None, "Email already exists"
    # Employee ID uniqueness check
    existing_empid = await db.employees.find_one({"employee_id": data["employee_id"]})
    if existing_empid:
        return None, "Employee ID already exists"
    if data.get("salary", 0) < 0:
        return None, "Salary must be non-negative"
    
    try:
        # Ensure status has a valid default
        status = data.get("status") or EmployeeStatus.ACTIVE
        
        employee_doc = prepare_employee_document(
            employee_id=data["employee_id"],
            name=data["name"],
            email=data["email"],
            role=data["role"],
            department=data["department"],
            salary=data["salary"],
            status=status,
            joining_date=data.get("joining_date"),
            promotion_history=data.get("promotion_history"),
            manager_id=data.get("manager_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )
        result = await db.employees.insert_one(employee_doc)
        employee_id = str(result.inserted_id)
        
        # Create a user account for the employee
        username = data["employee_id"].lower()  # Use employee_id as username
        password = data["employee_id"]  # Use employee_id as default password
        hashed_password = hash_password(password)
        
        # Map employee role to user role (case-insensitive)
        role_lower = data["role"].lower()
        role_mapping = {
            "employee": "employee",
            "manager": "manager",
            "hr": "hr",
            "admin": "admin"
        }
        user_role = role_mapping.get(role_lower, "employee")
        
        # Check if user already exists
        existing_user = await db.users.find_one({"username": username})
        if not existing_user:
            await db.users.insert_one({
                "username": username,
                "password": hashed_password,
                "role": user_role,
                "employee_id": data["employee_id"],
                "created_at": datetime.utcnow()
            })
        
        return employee_id, None
    except Exception as e:
        return None, f"Error creating employee: {str(e)}"

async def update_employee(db, employee_id: str, data: dict):
    if "email" in data:
        existing = await db.employees.find_one({"email": data["email"], "employee_id": {"$ne": employee_id}})
        if existing:
            return False, "Email already exists"
    if "employee_id" in data and data["employee_id"] != employee_id:
        existing = await db.employees.find_one({"employee_id": data["employee_id"]})
        if existing:
            return False, "Employee ID already exists"
    if "salary" in data and data["salary"] < 0:
        return False, "Salary must be non-negative"
    data["updated_at"] = datetime.utcnow()
    result = await db.employees.update_one({"employee_id": employee_id}, {"$set": data})
    return result.modified_count > 0, None

async def activate_employee(db, employee_id: str):
    result = await db.employees.update_one({"employee_id": employee_id}, {"$set": {"status": EmployeeStatus.ACTIVE, "updated_at": datetime.utcnow()}})
    return result.modified_count > 0

async def deactivate_employee(db, employee_id: str):
    result = await db.employees.update_one({"employee_id": employee_id}, {"$set": {"status": EmployeeStatus.INACTIVE, "updated_at": datetime.utcnow()}})
    return result.modified_count > 0

async def delete_employee(db, employee_id: str):
    result = await db.employees.delete_one({"employee_id": employee_id})
    return result.deleted_count > 0

async def get_all_employees(db, filters: dict = None, pagination: dict = None):
    query = filters or {}
    cursor = db.employees.find(query)
    if pagination:
        skip = pagination.get("skip", 0)
        limit = pagination.get("limit", 20)
        cursor = cursor.skip(skip).limit(limit)
    return await cursor.to_list(None)

async def total_employees(db):
    return await db.employees.count_documents({})

async def active_employees(db):
    return await db.employees.count_documents({"status": EmployeeStatus.ACTIVE})

async def department_wise_count(db):
    pipeline = [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
    return await db.employees.aggregate(pipeline).to_list(None)

async def role_wise_count(db):
    pipeline = [
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]
    return await db.employees.aggregate(pipeline).to_list(None)

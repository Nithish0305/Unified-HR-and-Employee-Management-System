from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from database import users_collection
from security import hash_password
from auth import router
from dependencies import get_current_user
from projects import router as project_router
from tasks import router as task_router
from tasks import tasks_collection
from projects import projects_collection
from progress_calculator import calculate_project_progress
from modules.leave.routes import router as leave_router
from modules.salary.routes import router as salary_router
from modules.meeting.routes import router as meeting_router
from modules.employee_management.routes import router as employee_router
from modules.employee_management.routes import router as employee_router



app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.include_router(router)
app.include_router(project_router)
app.include_router(task_router)
app.include_router(leave_router)
app.include_router(salary_router)
app.include_router(meeting_router)
app.include_router(employee_router)
# CREATE DEFAULT ADMIN ON STARTUP
@app.on_event("startup")
async def create_admin():
    admin = await users_collection.find_one({"username": "admin"})
    if not admin:
        await users_collection.insert_one({
            "username": "admin",
            "password": hash_password("admin123"),
            "role": "admin"
        })

# DASHBOARD
@app.get("/dashboard")
async def dashboard(request: Request, user=Depends(get_current_user), employee_id: str = None):
	pending_leaves = None
	employee_data = None
	user_role = user.get("role", "").lower()  # Convert to lowercase for case-insensitive comparison
	
	# Admin/HR Features - Pending leave approvals
	if user_role in ["admin", "hr"]:
		from modules.leave.routes import get_leaves_collection, extract_date
		leaves_collection = await get_leaves_collection()
		query = {"status": "Pending"}
		if employee_id:
			query["employee_id"] = employee_id
		leaves = await leaves_collection.find(query).sort("applied_on", -1).to_list(None)
		pending_leaves = [
			{
				"leave_id": leave["leave_id"],
				"employee_id": leave["employee_id"],
				"leave_type": leave["leave_type"],
				"start_date": str(extract_date(leave["start_date"])),
				"end_date": str(extract_date(leave["end_date"])),
				"reason": leave["reason"]
			}
			for leave in leaves
		]
	
	# Employee Features - Personal dashboard
	if user_role == "employee":
		employee_id = user.get("employee_id")
		if employee_id:
			from database import db
			
			# Get employee record
			employee = await db.employees.find_one({"employee_id": employee_id})
			if employee:
				# Get leaves
				leaves = await db.leaves.find({"employee_id": employee_id}).to_list(None)
				leaves_summary = {"approved": [], "rejected": [], "pending": []}
				for leave in leaves:
					summary = {
						"leave_type": leave.get("leave_type"),
						"start_date": str(leave.get("start_date", "")),
						"end_date": str(leave.get("end_date", "")),
						"reason": leave.get("reason"),
						"status": leave.get("status")
					}
					status = leave.get("status", "").lower()
					if status == "approved":
						leaves_summary["approved"].append(summary)
					elif status == "rejected":
						leaves_summary["rejected"].append(summary)
					elif status == "pending":
						leaves_summary["pending"].append(summary)
				
				# Get salary increments
				salary_increments = await db.salary_changes.find({"employee_id": employee_id}).to_list(None)
				salary_summary = {"approved": [], "rejected": [], "pending": []}
				for increment in salary_increments:
					summary = {
						"current_salary": float(increment.get("current_salary", 0)),
						"proposed_salary": float(increment.get("proposed_salary", 0)),
						"effective_date": str(increment.get("effective_date", "")),
						"reason": increment.get("reason"),
						"status": increment.get("status")
					}
					inc_status = increment.get("status", "").lower()
					if inc_status == "approved":
						salary_summary["approved"].append(summary)
					elif inc_status == "rejected":
						salary_summary["rejected"].append(summary)
					elif inc_status == "pending":
						salary_summary["pending"].append(summary)
				
				# Get promotions
				promotions = await db.promotions.find({"employee_id": employee_id}).to_list(None)
				promotions_summary = {"approved": [], "rejected": [], "pending": []}
				for promotion in promotions:
					summary = {
						"new_role": promotion.get("new_role"),
						"new_department": promotion.get("new_department"),
						"effective_date": str(promotion.get("effective_date", "")),
						"reason": promotion.get("reason"),
						"status": promotion.get("status")
					}
					promo_status = promotion.get("status", "").lower()
					if promo_status == "approved":
						promotions_summary["approved"].append(summary)
					elif promo_status == "rejected":
						promotions_summary["rejected"].append(summary)
					elif promo_status == "pending":
						promotions_summary["pending"].append(summary)
				
				# Get meetings
				meetings = await db.meetings.find({
					"participants": employee_id,
					"status": {"$in": ["Scheduled", "Completed"]}
				}).sort("date", 1).to_list(None)
				
				scheduled_meetings = []
				completed_meetings = []
				for meeting in meetings:
					meeting_summary = {
						"title": meeting.get("title"),
						"description": meeting.get("description"),
						"date": str(meeting.get("date", "")),
						"start_time": meeting.get("start_time"),
						"end_time": meeting.get("end_time"),
						"status": meeting.get("status")
					}
					if meeting.get("status") == "Completed":
						completed_meetings.append(meeting_summary)
					else:
						scheduled_meetings.append(meeting_summary)
				
				employee_data = {
					"employee": {
						"name": employee.get("name"),
						"email": employee.get("email"),
						"employee_id": employee_id,
						"role": employee.get("role"),
						"department": employee.get("department"),
						"salary": float(employee.get("salary", 0)),
						"status": employee.get("status") or "Active",
						"joining_date": str(employee.get("joining_date", ""))
					},
					"leaves": leaves_summary,
					"salary_increments": salary_summary,
					"promotions": promotions_summary,
					"meetings": {
						"scheduled": scheduled_meetings,
						"completed": completed_meetings
					},
					"summary": {
						"total_leaves_approved": len(leaves_summary["approved"]),
						"total_leaves_rejected": len(leaves_summary["rejected"]),
						"total_leaves_pending": len(leaves_summary["pending"]),
						"total_salary_requests": len(salary_increments),
						"total_promotions": len(promotions),
						"scheduled_meetings": len(scheduled_meetings),
						"completed_meetings": len(completed_meetings)
					}
				}
	
	return templates.TemplateResponse(
		"dashboard.html",
		{
			"request": request,
			"role": user["role"],
			"username": user["username"],
			"pending_leaves": pending_leaves,
			"employee_data": employee_data
		}
	)


@app.get("/dashboard/summary")
async def dashboard_summary(user=Depends(get_current_user)):

    if user["role"] == "admin":
        projects = await projects_collection.find().to_list(None)
        tasks = await tasks_collection.find().to_list(None)

        completed = len([t for t in tasks if t["status"] == "Completed"])

        return {
            "total_projects": len(projects),
            "total_tasks": len(tasks),
            "completed_tasks": completed
        }

    elif user["role"] == "manager":
        projects = await projects_collection.find(
            {"manager_id": user["_id"]}
        ).to_list(None)

        project_ids = [project["_id"] for project in projects]

        tasks = await tasks_collection.find(
            {"project_id": {"$in": project_ids}}
        ).to_list(None)

        completed = len([t for t in tasks if t["status"] == "Completed"])

        return {
            "total_projects": len(projects),
            "total_tasks": len(tasks),
            "completed_tasks": completed
        }

    else:  # employee
        tasks = await tasks_collection.find(
            {"assigned_to": user["_id"]}
        ).to_list(None)

        completed = len([t for t in tasks if t["status"] == "Completed"])

        return {
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "pending_tasks": len(tasks) - completed
        }


# DEBUG ENDPOINT - Check all employees in system
@app.get("/debug/employees")
async def debug_employees(user=Depends(get_current_user)):
    """Debug endpoint to list all employees in the system"""
    if user["role"] != "admin":
        return {"error": "Only admin can access this endpoint"}
    
    from database import db
    employees = await db.employees.find().to_list(None)
    return {
        "total_employees": len(employees),
        "employees": [
            {
                "_id": str(emp.get("_id")),
                "employee_id": emp.get("employee_id"),
                "name": emp.get("name"),
                "email": emp.get("email"),
                "status": emp.get("status")
            }
            for emp in employees
        ]
    }


# DEBUG ENDPOINT - Check specific employee
@app.get("/debug/employee/{employee_id}")
async def debug_employee(employee_id: str, user=Depends(get_current_user)):
    """Debug endpoint to check if an employee exists"""
    if user["role"] != "admin":
        return {"error": "Only admin can access this endpoint"}
    
    from database import db
    employee = await db.employees.find_one({"employee_id": employee_id})
    
    if not employee:
        return {"status": "not_found", "employee_id": employee_id}
    
    return {
        "status": "found",
        "_id": str(employee.get("_id")),
        "employee_id": employee.get("employee_id"),
        "name": employee.get("name"),
        "email": employee.get("email"),
        "department": employee.get("department"),
        "role": employee.get("role"),
        "salary": employee.get("salary"),
        "status": employee.get("status")
    }
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



app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.include_router(router)
app.include_router(project_router)
app.include_router(task_router)
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
async def dashboard(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "role": user["role"], "username": user["username"]}
    )


@app.get("/dashboard/summary")
async def dashboard_summary(user=Depends(get_current_user)):

    if user["role"] == "admin":
        projects = await projects_collection.find().to_list(None)
        tasks = await tasks_collection.find().to_list(None)

    elif user["role"] == "manager":
        projects = await projects_collection.find(
            {"manager_id": user["_id"]}
        ).to_list(None)

        project_ids = [project["_id"] for project in projects]

        tasks = await tasks_collection.find(
            {"project_id": {"$in": project_ids}}
        ).to_list(None)

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

    completed = len([t for t in tasks if t["status"] == "Completed"])

    return {
        "total_projects": len(projects),
        "total_tasks": len(tasks),
        "completed_tasks": completed
    }
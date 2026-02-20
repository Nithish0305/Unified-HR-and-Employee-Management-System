from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId

from database import db
from dependencies import get_current_user, require_role

router = APIRouter(prefix="/tasks", tags=["Tasks"])

tasks_collection = db.tasks
projects_collection = db.projects
users_collection = db.users

@router.post("/project/{project_id}")
async def create_task(
    project_id: str,
    title: str,
    description: str,
    assigned_username: str,
    weight: int,
    priority: str,
    deadline: str,
    user=Depends(require_role("manager"))
):
    # Validate project exists
    project = await projects_collection.find_one(
        {"_id": ObjectId(project_id)}
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ensure manager owns project
    if project["manager_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Validate employee
    employee = await users_collection.find_one(
        {"username": assigned_username, "role": "employee"}
    )

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight must be > 0")

    task = {
        "project_id": project["_id"],
        "title": title,
        "description": description,
        "assigned_to": employee["_id"],
        "status": "To-Do",
        "weight": weight,
        "priority": priority,
        "deadline": deadline,
        "comments": [],
        "created_at": datetime.utcnow()
    }

    result = await tasks_collection.insert_one(task)

    return {
        "message": "Task created successfully",
        "task_id": str(result.inserted_id)
    }

@router.patch("/{task_id}/status")
async def update_status(
    task_id: str,
    status: str,
    user=Depends(get_current_user)
):
    task = await tasks_collection.find_one(
        {"_id": ObjectId(task_id)}
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["assigned_to"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    if status not in ["To-Do", "In Progress", "Completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Update task
    await tasks_collection.update_one(
        {"_id": task["_id"]},
        {"$set": {"status": status}}
    )

    # 🔥 AUTO PROJECT STATUS UPDATE
    project_id = task["project_id"]

    project_tasks = await tasks_collection.find(
        {"project_id": project_id}
    ).to_list(None)

    if project_tasks:  # only if tasks exist
        all_completed = all(
            t["status"] == "Completed" for t in project_tasks
        )

        new_status = "Completed" if all_completed else "Active"

        await projects_collection.update_one(
            {"_id": project_id},
            {"$set": {"status": new_status}}
        )

    return {"message": "Status updated successfully"}



@router.post("/{task_id}/comment")
async def add_comment(
    task_id: str,
    text: str,
    user=Depends(get_current_user)
):
    task = await tasks_collection.find_one(
        {"_id": ObjectId(task_id)}
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Employee must be assigned OR manager must own project
    project = await projects_collection.find_one(
        {"_id": task["project_id"]}
    )

    if not (
        task["assigned_to"] == user["_id"] or
        project["manager_id"] == user["_id"]
    ):
        raise HTTPException(status_code=403, detail="Not authorized")

    comment = {
        "commented_by": user["_id"],
        "text": text,
        "created_at": datetime.utcnow()
    }

    await tasks_collection.update_one(
        {"_id": task["_id"]},
        {"$push": {"comments": comment}}
    )

    return {"message": "Comment added"}

@router.get("/project/{project_id}")
async def get_tasks_by_project(
    project_id: str,
    user=Depends(get_current_user)
):
    project = await projects_collection.find_one(
        {"_id": ObjectId(project_id)}
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # RBAC
    if user["role"] == "manager":
        if project["manager_id"] != user["_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

        tasks = await tasks_collection.find(
            {"project_id": ObjectId(project_id)}
        ).to_list(None)

    elif user["role"] == "employee":
        tasks = await tasks_collection.find(
            {
                "project_id": ObjectId(project_id),
                "assigned_to": user["_id"]
            }
        ).to_list(None)

    else:  # admin
        tasks = await tasks_collection.find(
            {"project_id": ObjectId(project_id)}
        ).to_list(None)

    # Serialize everything safely
    for task in tasks:
        task["_id"] = str(task["_id"])
        task["project_id"] = str(task["project_id"])
        task["assigned_to"] = str(task["assigned_to"])

        for comment in task.get("comments", []):
            comment["commented_by"] = str(comment["commented_by"])

    return tasks


@router.get("/my")
async def get_my_tasks(user=Depends(require_role("employee"))):

    tasks = await tasks_collection.find(
        {"assigned_to": user["_id"]}
    ).to_list(None)

    for task in tasks:
        task["_id"] = str(task["_id"])
        task["project_id"] = str(task["project_id"])
        task["assigned_to"] = str(task["assigned_to"])

        # 🔥 FIX FOR COMMENTS
        for comment in task.get("comments", []):
            comment["commented_by"] = str(comment["commented_by"])

    return tasks


@router.patch("/{task_id}")
async def manager_update_task(
    task_id: str,
    title: str = None,
    description: str = None,
    weight: int = None,
    priority: str = None,
    deadline: str = None,
    user=Depends(require_role("manager"))
):
    task = await tasks_collection.find_one(
        {"_id": ObjectId(task_id)}
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await projects_collection.find_one(
        {"_id": task["project_id"]}
    )

    if project["manager_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = {}

    if title:
        update_data["title"] = title
    if description:
        update_data["description"] = description
    if weight is not None:
        update_data["weight"] = weight
    if priority:
        update_data["priority"] = priority
    if deadline:
        update_data["deadline"] = deadline

    await tasks_collection.update_one(
        {"_id": task["_id"]},
        {"$set": update_data}
    )

    return {"message": "Task updated successfully"}
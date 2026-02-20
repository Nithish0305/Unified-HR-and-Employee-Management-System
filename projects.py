from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId
from database import db
from dependencies import get_current_user, require_role
from progress_calculator import calculate_project_progress

router = APIRouter(prefix="/projects", tags=["Projects"])

projects_collection = db.projects
tasks_collection = db.tasks

@router.post("/")
async def create_project(
    name: str,
    description: str,
    deadline: str,
    user=Depends(require_role("manager"))
):
    project = {
        "name": name,
        "description": description,
        "manager_id": user["_id"],
        "deadline": deadline,
        "status": "Active",
        "created_at": datetime.utcnow()
    }

    result = await projects_collection.insert_one(project)

    return {
        "message": "Project created successfully",
        "project_id": str(result.inserted_id)
    }


@router.get("/")
async def get_projects(user=Depends(get_current_user)):

    if user["role"] == "admin":
        projects = await projects_collection.find().to_list(None)

    elif user["role"] == "manager":
        projects = await projects_collection.find(
            {"manager_id": user["_id"]}
        ).to_list(None)

    else:  # employee
        tasks = await tasks_collection.find(
            {"assigned_to": user["_id"]}
        ).to_list(None)

        project_ids = list({task["project_id"] for task in tasks})

        projects = await projects_collection.find(
            {"_id": {"$in": project_ids}}
        ).to_list(None)

    final_projects = []

    for project in projects:

        # Get tasks for this project
        tasks = await tasks_collection.find(
            {"project_id": project["_id"]}
        ).to_list(None)

        # Calculate progress
        progress = calculate_project_progress(tasks)

        # Serialize ObjectIds
        project["_id"] = str(project["_id"])
        project["manager_id"] = str(project["manager_id"])
        project["progress"] = progress

        final_projects.append(project)

    return final_projects

@router.get("/{project_id}")
async def get_single_project(
    project_id: str,
    user=Depends(get_current_user)
):
    project = await projects_collection.find_one(
        {"_id": ObjectId(project_id)}
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Access control
    if user["role"] == "manager":
        if project["manager_id"] != user["_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

    elif user["role"] == "employee":
        task = await tasks_collection.find_one({
            "project_id": project["_id"],
            "assigned_to": user["_id"]
        })
        if not task:
            raise HTTPException(status_code=403, detail="Not authorized")

    # Fetch tasks for progress calculation
    tasks = await tasks_collection.find(
        {"project_id": project["_id"]}
    ).to_list(None)

    progress = calculate_project_progress(tasks)

    project["_id"] = str(project["_id"])
    project["manager_id"] = str(project["manager_id"])
    project["progress"] = progress

    return project

@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    name: str = None,
    description: str = None,
    deadline: str = None,
    user=Depends(require_role("manager"))
):
    project = await projects_collection.find_one(
        {"_id": ObjectId(project_id)}
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project["manager_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = {}

    if name:
        update_data["name"] = name
    if description:
        update_data["description"] = description
    if deadline:
        update_data["deadline"] = deadline

    await projects_collection.update_one(
        {"_id": project["_id"]},
        {"$set": update_data}
    )

    return {"message": "Project updated successfully"}




@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user=Depends(require_role("admin"))
):
    project = await projects_collection.find_one(
        {"_id": ObjectId(project_id)}
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete tasks under project
    await tasks_collection.delete_many(
        {"project_id": project["_id"]}
    )

    # Delete project
    await projects_collection.delete_one(
        {"_id": project["_id"]}
    )

    return {"message": "Project and related tasks deleted"}
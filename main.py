from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from database import users_collection
from security import hash_password
from auth import router
from dependencies import get_current_user

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.include_router(router)

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

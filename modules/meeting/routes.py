from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from bson import ObjectId
from .schemas import MeetingCreate, MeetingResponse
from .service import create_meeting, check_availability, cancel_meeting, get_user_meetings
from .models import MeetingStatus

# Placeholder for dependency
from dependencies import get_current_user
# Placeholder for db
from database import db
from employee_validator import validate_employees_exist

router = APIRouter(prefix="/meetings", tags=["Meeting"])

@router.post("", response_model=MeetingResponse)
async def create_meeting_endpoint(meeting: MeetingCreate, current_user: dict = Depends(get_current_user)):
	# Verify all participants exist in the system using centralized validator
	await validate_employees_exist(meeting.participants)
	
	conflicts = await check_availability(db, meeting.date, meeting.start_time, meeting.end_time, meeting.participants)
	if conflicts:
		raise HTTPException(status_code=400, detail="Meeting time conflicts with existing meetings.")
	meeting_data = meeting.dict()
	meeting_id = await create_meeting(db, meeting_data, current_user)
	return MeetingResponse(
		id=meeting_id,
		title=meeting.title,
		date=meeting.date,
		start_time=meeting.start_time,
		end_time=meeting.end_time,
		status=MeetingStatus.SCHEDULED
	)

@router.get("", response_model=List[MeetingResponse])
async def get_meetings(current_user: dict = Depends(get_current_user)):
	meetings = await get_user_meetings(db, current_user)
	return [
		MeetingResponse(
			id=str(m["_id"]),
			title=m["title"],
			date=m["date"],
			start_time=m.get("start_time"),
			end_time=m.get("end_time"),
			status=m["status"]
		) for m in meetings
	]

@router.get("/{id}", response_model=MeetingResponse)
async def get_meeting(id: str, current_user: dict = Depends(get_current_user)):
	meeting = await db.meetings.find_one({"_id": ObjectId(id)})
	if not meeting:
		raise HTTPException(status_code=404, detail="Meeting not found.")
	user_id = str(current_user["_id"])
	if user_id != meeting["organizer_id"] and user_id not in meeting["participants"]:
		raise HTTPException(status_code=403, detail="Not authorized to view this meeting.")
	return MeetingResponse(
		id=str(meeting["_id"]),
		title=meeting["title"],
		date=meeting["date"],
		start_time=meeting.get("start_time"),
		end_time=meeting.get("end_time"),
		status=meeting["status"]
	)

@router.patch("/{id}/cancel")
async def cancel_meeting_endpoint(id: str, current_user: dict = Depends(get_current_user)):
	meeting = await db.meetings.find_one({"_id": ObjectId(id)})
	if not meeting:
		raise HTTPException(status_code=404, detail="Meeting not found.")
	user_id = str(current_user["_id"])
	if user_id != meeting["organizer_id"]:
		raise HTTPException(status_code=403, detail="Only organizer can cancel meeting.")
	success, msg = await cancel_meeting(db, id, current_user)
	if not success:
		raise HTTPException(status_code=400, detail=msg)
	return {"message": msg}

@router.post("/check-availability")
async def check_availability_endpoint(meeting: MeetingCreate, current_user: dict = Depends(get_current_user)):
	conflicts = await check_availability(db, meeting.date, meeting.start_time, meeting.end_time, meeting.participants)
	return {"conflicts": [
		{
			"id": str(m["_id"]),
			"title": m["title"],
			"date": m["date"],
			"status": m["status"]
		} for m in conflicts
	]}

from datetime import datetime, date
from bson import ObjectId
from .models import MeetingStatus

async def create_meeting(db, meeting_data: dict, user: dict):
    meeting_data["organizer_id"] = str(user["_id"])
    meeting_data["status"] = MeetingStatus.SCHEDULED
    meeting_data["created_at"] = datetime.utcnow()
    meeting_data["updated_at"] = datetime.utcnow()
    # Store only the date part as string
    if hasattr(meeting_data["date"], "date"):
        meeting_data["date"] = meeting_data["date"].date().strftime("%Y-%m-%d")
    elif isinstance(meeting_data["date"], datetime):
        meeting_data["date"] = meeting_data["date"].strftime("%Y-%m-%d")
    elif isinstance(meeting_data["date"], date):
        meeting_data["date"] = meeting_data["date"].strftime("%Y-%m-%d")
    # Convert start_time and end_time to integer minutes
    def time_to_minutes(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m
    meeting_data["start_time_minutes"] = time_to_minutes(meeting_data["start_time"])
    meeting_data["end_time_minutes"] = time_to_minutes(meeting_data["end_time"])
    result = await db.meetings.insert_one(meeting_data)
    return str(result.inserted_id)

async def check_availability(db, date: datetime, start_time: str, end_time: str, participants: list[str]):
    # Extract just the date part and format it as YYYY-MM-DD
    if isinstance(date, datetime):
        date_str = date.strftime("%Y-%m-%d")
    else:
        # If it's already a string, ensure it's just the date part
        date_str = str(date)[:10] if isinstance(date, str) else str(date)
    
    # Convert start_time and end_time to integer minutes
    def time_to_minutes(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    
    # Query for conflicts:
    # 1. Same date
    # 2. Not cancelled  
    # 3. Any participant in common
    # 4. Time overlap: new_start < existing_end AND new_end > existing_start
    query = {
        "date": {"$regex": f"^{date_str}"},  # Match dates starting with YYYY-MM-DD
        "status": {"$ne": MeetingStatus.CANCELLED},
        "participants": {"$in": participants},
        "start_time_minutes": {"$exists": True},
        "end_time_minutes": {"$exists": True},
        "$expr": {
            "$and": [
                {"$lt": ["$start_time_minutes", end_minutes]},
                {"$gt": ["$end_time_minutes", start_minutes]}
            ]
        }
    }
    conflicts = await db.meetings.find(query).to_list(None)
    return conflicts

async def cancel_meeting(db, meeting_id: str, user: dict):
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        return False, "Meeting not found"
    user_id = str(user["_id"])
    if meeting["organizer_id"] != user_id:
        return False, "Only organizer can cancel meeting"
    if meeting["status"] == MeetingStatus.CANCELLED:
        return False, "Meeting already cancelled"
    await db.meetings.update_one(
        {"_id": ObjectId(meeting_id)},
        {"$set": {"status": MeetingStatus.CANCELLED, "updated_at": datetime.utcnow()}}
    )
    return True, "Meeting cancelled"

async def get_user_meetings(db, user: dict):
    user_id = str(user["_id"])
    query = {
        "$or": [
            {"organizer_id": user_id},
            {"participants": user_id}
        ],
        "status": {"$ne": MeetingStatus.CANCELLED}
    }
    meetings = await db.meetings.find(query).to_list(None)
    return meetings

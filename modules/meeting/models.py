from datetime import datetime
from enum import Enum

class MeetingStatus(str, Enum):
	SCHEDULED = "Scheduled"
	CANCELLED = "Cancelled"
	COMPLETED = "Completed"

def prepare_meeting_document(
	title: str,
	description: str,
	date: datetime,
	start_time: str,
	end_time: str,
	organizer_id: str,
	participants: list[str],
	status: str = MeetingStatus.SCHEDULED,
	reminder_sent: bool = False,
	created_at: datetime = None,
	updated_at: datetime = None
) -> dict:
	"""
	Prepare a meeting document for MongoDB insertion.
	"""
	now = datetime.utcnow()
	meeting_doc = {
		"title": title,
		"description": description,
		"date": date,
		"start_time": start_time,
		"end_time": end_time,
		"organizer_id": organizer_id,
		"participants": participants,
		"status": status,
		"reminder_sent": reminder_sent,
		"created_at": created_at or now,
		"updated_at": updated_at or now
	}
	return meeting_doc

from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime, date as dt_date

class MeetingCreate(BaseModel):
	title: str = Field(..., description="Meeting title")
	description: Optional[str] = Field(None, description="Meeting description")
	date: datetime = Field(..., description="Meeting date and time")
	start_time: str = Field(..., description="Start time (HH:MM)")
	end_time: str = Field(..., description="End time (HH:MM)")
	participants: List[str] = Field(..., description="List of participant IDs")

	@validator("date")
	def date_not_in_past(cls, v):
		from datetime import datetime
		# Use utcnow() to get naive datetime for comparison with incoming datetime
		now = datetime.utcnow()
		# Handle both naive and aware datetimes
		if v.tzinfo is not None and now.tzinfo is None:
			now = now.replace(tzinfo=v.tzinfo)
		elif v.tzinfo is None and now.tzinfo is not None:
			v = v.replace(tzinfo=now.tzinfo)
		if v < now:
			raise ValueError("Meeting date must not be in the past.")
		return v

	@validator("end_time")
	def start_time_before_end_time(cls, v, values):
		start = values.get("start_time")
		if start and v:
			try:
				start_dt = datetime.strptime(start, "%H:%M")
				end_dt = datetime.strptime(v, "%H:%M")
			except Exception:
				raise ValueError("Time must be in HH:MM format.")
			if end_dt <= start_dt:
				raise ValueError("End time must be after start time.")
		return v

class MeetingResponse(BaseModel):
	id: str = Field(..., description="Meeting ID")
	title: str = Field(..., description="Meeting title")
	date: datetime = Field(..., description="Meeting date and time")
	start_time: Optional[str] = Field(None, description="Start time (HH:MM)")
	end_time: Optional[str] = Field(None, description="End time (HH:MM)")
	status: str = Field(..., description="Meeting status")

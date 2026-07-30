import csv
import hashlib
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.config.database import get_db
from src.models.engagement_log import EngagementLog
from src.models.session import Session as DBSession

router = APIRouter(
    prefix="/api/export",
    tags=["Export"],
)

def anonymize_id(user_id: int) -> str:
    """Takes a real user ID and turns it into a safe, random-looking string."""
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:10]
    return f"anon_{digest}"

def generate_csv(data_generator):
    """
    Takes our data row by row and turns it into a CSV format.
    Using a generator helps us send large files without crashing the server.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write the header row first
    writer.writerow([
        "timestamp", 
        "anonymized_student_id", 
        "engagement_score", 
        "state", 
        "drowsiness_count", 
        "negative_expression_count", 
        "distracted_count", 
        "phone_detected_count"
    ])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    # Write each row of data
    for log in data_generator:
        writer.writerow([
            log.timestamp.isoformat(),
            anonymize_id(log.user_id),
            log.engagement_score,
            log.state.value if hasattr(log.state, 'value') else log.state,
            log.drowsiness_count,
            log.negative_expression_count,
            log.distracted_count,
            log.phone_detected_count
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

def generate_json(data_generator):
    """
    Sends the data as a JSON list. 
    It yields one piece at a time so it streams smoothly.
    """
    yield "[\n"
    first = True
    for log in data_generator:
        if not first:
            yield ",\n"
        first = False
        
        # Build a simple dictionary for this row
        row = {
            "timestamp": log.timestamp.isoformat(),
            "anonymized_student_id": anonymize_id(log.user_id),
            "engagement_score": log.engagement_score,
            "state": log.state.value if hasattr(log.state, 'value') else log.state,
            "drowsiness_count": log.drowsiness_count,
            "negative_expression_count": log.negative_expression_count,
            "distracted_count": log.distracted_count,
            "phone_detected_count": log.phone_detected_count
        }
        yield json.dumps(row)
    
    yield "\n]"

@router.get("/sessions/{session_id}")
def export_session(
    session_id: int,
    format: str = Query(..., description="Format to export: 'csv' or 'json'"),
    start: Optional[datetime] = Query(None, description="Start date filter"),
    end: Optional[datetime] = Query(None, description="End date filter"),
    student_id: Optional[int] = Query(None, description="Filter by specific student"),
    db: Session = Depends(get_db)
):
    """Downloads all engagement logs for a specific session."""
    
    # Build the database query step by step
    query = select(EngagementLog).where(EngagementLog.session_id == session_id)
    
    # Apply optional filters if they were provided
    if start:
        query = query.where(EngagementLog.timestamp >= start)
    if end:
        query = query.where(EngagementLog.timestamp <= end)
    if student_id:
        query = query.where(EngagementLog.user_id == student_id)
        
    # Order by time so it reads naturally
    query = query.order_by(EngagementLog.timestamp)
    
    # Get the data in chunks of 1000
    data_generator = db.scalars(query).yield_per(1000)

    # Return as CSV or JSON
    if format.lower() == "csv":
        return StreamingResponse(
            generate_csv(data_generator),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=session_{session_id}.csv"}
        )
    elif format.lower() == "json":
        return StreamingResponse(
            generate_json(data_generator),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=session_{session_id}.json"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'json'.")

@router.get("/courses/{course_id}")
def export_course(
    course_id: int,
    format: str = Query(..., description="Format to export: 'csv' or 'json'"),
    start: Optional[datetime] = Query(None, description="Start date filter"),
    end: Optional[datetime] = Query(None, description="End date filter"),
    student_id: Optional[int] = Query(None, description="Filter by specific student"),
    db: Session = Depends(get_db)
):
    """Downloads all engagement logs for an entire course."""
    
    # Find all logs that belong to sessions linked to this course
    query = (
        select(EngagementLog)
        .join(DBSession, EngagementLog.session_id == DBSession.id)
        .where(DBSession.course_id == course_id)
    )
    
    if start:
        query = query.where(EngagementLog.timestamp >= start)
    if end:
        query = query.where(EngagementLog.timestamp <= end)
    if student_id:
        query = query.where(EngagementLog.user_id == student_id)
        
    query = query.order_by(EngagementLog.timestamp)
    data_generator = db.scalars(query).yield_per(1000)

    if format.lower() == "csv":
        return StreamingResponse(
            generate_csv(data_generator),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=course_{course_id}.csv"}
        )
    elif format.lower() == "json":
        return StreamingResponse(
            generate_json(data_generator),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=course_{course_id}.json"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'json'.")

"""
Admin endpoints for manual job triggering and management.
"""

import structlog
from fastapi import APIRouter, HTTPException

from scheduler.jobs import daily_checkin_job

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/trigger-checkins")
async def trigger_checkins():
    try:
        logger.info("manual_checkin_trigger_requested")
    
        daily_checkin_job()
        
        logger.info("manual_checkin_trigger_completed")
        
        return {
            "status": "success",
            "message": "Daily check-in job executed successfully",
            "job": "daily_checkin"
        }
    
    except Exception as e:
        logger.error("manual_checkin_trigger_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute check-in job: {str(e)}"
        )

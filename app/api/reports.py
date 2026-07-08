from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.report_generator import build_master_audit_workbook


router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/master/download")
def download_master_report(db: Session = Depends(get_db)) -> StreamingResponse:
    output = build_master_audit_workbook(db)
    filename = f"sap_user_tracker_master_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db.screenshots import get_screenshot


router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence"])


@router.get("/screenshots/{screenshot_id}")
def get_screenshot_evidence(screenshot_id: str):
    image = get_screenshot(screenshot_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Screenshot evidence not found")
    return StreamingResponse(
        image,
        media_type="image/png",
        headers={"Content-Length": str(image.length), "Cache-Control": "private, max-age=300"},
    )

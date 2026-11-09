from io import BytesIO

from bson import ObjectId
from gridfs import GridFSBucket

from app.db.mongodb import db


bucket = GridFSBucket(db, bucket_name="change_screenshots")


def save_screenshot(
    image: bytes,
    filename: str,
    metadata: dict,
) -> str:
    file_id = bucket.upload_from_stream(
        filename,
        BytesIO(image),
        metadata=metadata,
    )
    return str(file_id)


def get_screenshot(file_id: str):
    try:
        return bucket.open_download_stream(ObjectId(file_id))
    except Exception:
        return None

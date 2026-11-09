from pymongo import MongoClient

from app.core.config import settings


client = MongoClient(settings.mongo_uri)

db = client[settings.mongo_db]


def check_database_connection() -> bool:
    try:
        client.admin.command("ping")
        return True
    except Exception:
        return False
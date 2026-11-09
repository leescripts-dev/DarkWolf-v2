from app.db.mongodb import db

collection = db["observations"]

unique_ids = collection.distinct(
    "source_id",
    {"source": "inc_ransom"}
)

print("Unique Inc Ransom victims:", len(unique_ids))
from app.db.mongodb import db

collection = db["observations"]

pipeline = [
    {
        "$group": {
            "_id": "$source_id",
            "count": {"$sum": 1},
        }
    },
    {
        "$match": {
            "count": {"$gt": 1}
        }
    },
    {
        "$sort": {
            "count": -1
        }
    }
]

results = list(collection.aggregate(pipeline))

print("Victims with multiple observations:", len(results))

for item in results:
    print(item)
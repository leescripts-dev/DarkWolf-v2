import json

from app.collection.runner import collect_inc_ransom_page


if __name__ == "__main__":
    result = collect_inc_ransom_page(
        page=1,
        per_page=3,
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )
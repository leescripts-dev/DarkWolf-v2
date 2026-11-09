from app.collection.service import (
    IncRansomCollectionService,
)


def collect_inc_ransom_page(
    page: int = 1,
    per_page: int = 15,
):
    service = IncRansomCollectionService()

    result = service.collect_page(
        page=page,
        per_page=per_page,
    )

    return result.model_dump()
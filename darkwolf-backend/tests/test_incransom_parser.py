from app.sites.inc_ransom.parser import parse_announcement


raw = {
    "_id": "6abe94e19cd108bf26a37cde",
    "company": {
        "company_name": "Grupo%20Caberj",
        "country": "BR",
        "revenue": 57000000,
    },
    "categories": [
        "Proof"
    ],
    "description": [
        "Passaram%2017%20dias%20o%20administrador%20de%20fotos%20ainda%20n%C3%A3o%20corrigiu%20os%20erros."
    ],
    "logo": "6abe94e19cd108bf26a37cd6",
    "proof": [
        "6abe94e19cd108bf26a37cd3"
    ],
    "visits": 594,
    "leakAt": 1790875020000,
    "createdAt": 1790874849447,
    "updatedAt": 1790874918029,
}


announcement = parse_announcement(raw)

print(announcement.model_dump_json(indent=2))
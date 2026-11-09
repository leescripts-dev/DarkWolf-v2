from app.entities.organization_domain_extractor import extract_domains

tests = [
    "Imperial Valley Respite (ivrespite.com)",
    "Biomedical Caledonia Medical Laboratory (calmedlab.local)",
    "Black Creek Community Health Centre (bcch.local)",
    "San Francisco Sheriff's Department (sjcso.local)",
    "Norther n Bedford County School District (nbcsc.org)",
    "Center for Human Capital Innovation (centerforhci.org)",
    "City of Buckeye (buckeyeaz.gov)",
]

for text in tests:
    print(f"{text}")
    print(" ->", extract_domains(text))
    print()
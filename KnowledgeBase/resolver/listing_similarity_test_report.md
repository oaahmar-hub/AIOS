# AIOS Listing Similarity Match Report

- total tests: 21
- url-like tests: 11
- text-only tests: 10
- classification: LIVE
- url tests >=80 confidence: 10
- url tests >=90 confidence: 8

## Ocean Heights Query
- input: `https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html`
- parsed: {"platform": "propertyfinder.ae", "listing_id": "84894360", "transaction": "buy", "property_type": "apartment", "area": "Dubai Marina", "project": "", "building": "ocean heights", "unit": "", "bedrooms": "", "size": "", "price": "", "status_tokens": "", "permit_number": "", "property_number": "", "plot_number": "", "land_number": "", "municipality_number": "", "dewa_number": "", "source_platform": "propertyfinder.ae", "source_file": "", "source_chat_group": ""}
- top status: LIKELY_MATCH score=80
- Top 5 candidates:
  - id=raw-e6d971645320b9b2 area=Dubai Marina project= building=ocean heights bedrooms=2 size=148.64 sqm score=80 confidence=LIKELY_MATCH file=raw_chat_style_dataset

## URL test outcomes
- ocean_heights | status=LIKELY_MATCH | score=80
  - id=raw-e6d971645320b9b2 area=Dubai Marina project= building=ocean heights score=80 conf=LIKELY_MATCH source=raw_chat_style_dataset
- url_1 | status=PARTIAL | score=65
  - id=7f9f69f79ea5c7e8 area= project= building=preview contenthash renderstate score=65 conf=PARTIAL source=WhatsApp ChatStorage.sqlite
- url_2 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area=Business Bay project= building=damac maison prive score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
  - id=7f9f69f79ea5c7e8 area=Business Bay project= building=damac maison prive score=83 conf=LIKELY_MATCH source=WhatsApp ChatStorage.sqlite
- url_3 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area= project= building=samana golf avenue score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
- url_4 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area=MBR City project= building=sheikh score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
- url_5 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area= project= building=difc sky gardens difc sky gardens score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
- url_6 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area=Arjan project= building=samana park views samana park views score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
  - id=7f9f69f79ea5c7e8 area=Arjan project= building=samana park views samana park views score=40 conf=UNRESOLVED source=WhatsApp ChatStorage.sqlite
- url_7 | status=LIKELY_MATCH | score=80
  - id=7f9f69f79ea5c7e8 area=Arjan project= building=avelon boulevard avelon boulevard score=80 conf=LIKELY_MATCH source=WhatsApp ChatStorage.sqlite
- url_8 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area= project= building=barsha 1 atria score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
- url_9 | status=RESOLVED | score=100
  - id=7f9f69f79ea5c7e8 area=Business Bay project=Tiger building=tiger sky tower tiger sky score=100 conf=RESOLVED source=WhatsApp ChatStorage.sqlite
- url_10 | status=RESOLVED | score=93
  - id=7f9f69f79ea5c7e8 area= project= building=com score=93 conf=RESOLVED source=WhatsApp ChatStorage.sqlite

## Text-only test outcomes
- text_only_1 | status=UNRESOLVED | score=20
- text_only_2 | status=UNRESOLVED | score=20
- text_only_3 | status=UNRESOLVED | score=35
- text_only_4 | status=UNRESOLVED | score=40
- text_only_5 | status=UNRESOLVED | score=36
- text_only_6 | status=UNRESOLVED | score=36
- text_only_7 | status=UNRESOLVED | score=42
- text_only_8 | status=UNRESOLVED | score=40
- text_only_9 | status=UNRESOLVED | score=40
- text_only_10 | status=UNRESOLVED | score=36

## Failure summary
- below_65: 10
- partially_matched: 1

- list file: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/listing_similarity_candidates.csv`
- report file: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/listing_similarity_test_report.md`

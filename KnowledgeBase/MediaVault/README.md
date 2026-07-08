# MediaVault — real media only

`media_index.json` maps customer requests to REAL asset URLs (photos, floor
plans, brochures) that the WhatsApp brain is allowed to send. Empty index =
the brain honestly says "I'll check and send it shortly" — it never invents
or describes media it doesn't have.

Entry format:

    [{"keywords": ["verdana", "فيردانا"],
      "kind": "photos",
      "url": "https://drive.google.com/uc?id=FILE_ID",
      "caption": "Verdana - site photos (July 2026)"}]

Rules: https URLs only, hand-curated, one entry per asset. Keywords are
case-insensitive substrings matched against the inbound message.

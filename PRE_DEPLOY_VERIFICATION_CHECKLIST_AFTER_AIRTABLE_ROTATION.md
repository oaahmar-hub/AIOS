# FINAL PRE-DEPLOY VERIFICATION CHECKLIST

Status: WAITING

Do not run this until Omar confirms the Airtable PAT in `config.env` has been rotated.

Do not deploy.

Do not push to GitHub.

## Gate

- Omar confirms the old Airtable PAT was revoked/rotated in Airtable.
- Local `config.env` now contains the new Airtable PAT.
- The old revoked PAT is available only as a temporary shell env var for invalidation testing.

## Required command

From:

`/Users/hassanka/Downloads/AIOS`

Run:

```bash
AIOS_OLD_AIRTABLE_TOKEN='<revoked-old-token>' \
python3 00_FOUNDATION/scripts/pre_deploy_verify_after_airtable_rotation.py \
  --omar-confirmed-airtable-rotation
```

Notes:

- Do not paste the token into chat.
- Do not store the old token in any file.
- The script writes the report to:
  `00_FOUNDATION/PRE_DEPLOY_VERIFICATION_AFTER_AIRTABLE_ROTATION_RESULT.md`

## Checklist enforced by the script

1. New Airtable token works.
2. Old Airtable token is invalid.
3. `config.env` is still gitignored and not tracked.
4. No real secrets exist in tracked/shareable files.
5. Webhook secret enforcement still passes.
6. Basic Auth still passes.
7. Hosted backend router copy is still synced.
8. Python compile passes.
9. Railway env vars are ready.
10. Final classification is `READY` or `BLOCKED`.

## Expected outcome

- `READY`: pre-deploy security gate passes.
- `BLOCKED`: at least one required condition failed. Do not deploy until corrected and re-run.

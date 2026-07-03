# Final Pre-Deploy Verification After Airtable Rotation

Status: BLOCKED until Omar confirms Airtable PAT rotation is complete.

Purpose: run the final pre-deploy gate after the Airtable token has been rotated, without deploying, without pushing to GitHub, and without printing any secrets.

## Required Inputs

1. Omar confirmation that the Airtable PAT rotation is complete.
2. The current token already saved locally in:
   `/Users/hassanka/Downloads/AIOS/config.env`
3. The old revoked token available only as a temporary shell env var so the verifier can prove it is invalid.

## Run

From the AIOS root:

```bash
cd /Users/hassanka/Downloads/AIOS
export AIOS_OLD_AIRTABLE_TOKEN='<revoked_old_token>'
python3 00_FOUNDATION/scripts/pre_deploy_verify_after_airtable_rotation.py \
  --omar-confirmed-airtable-rotation
unset AIOS_OLD_AIRTABLE_TOKEN
```

The script writes the final report to:

`/Users/hassanka/Downloads/AIOS/00_FOUNDATION/PRE_DEPLOY_VERIFICATION_AFTER_AIRTABLE_ROTATION_RESULT.md`

## What It Verifies

1. New Airtable token works.
2. Old Airtable token is invalid.
3. `config.env` is still gitignored.
4. No real secrets exist in tracked files.
5. Webhook secret enforcement still passes.
6. Basic Auth still passes.
7. Hosted backend router copy is still synced.
8. Python compile passes.
9. Railway env vars are ready.
10. Final classification is `READY` or `BLOCKED`.

## Output Rules

- No token values are printed.
- No raw Railway variable values are printed.
- No deploy is triggered.
- No GitHub push happens.

## Classification Rule

- `READY`: every gate passes.
- `BLOCKED`: any gate fails or Omar confirmation is missing.

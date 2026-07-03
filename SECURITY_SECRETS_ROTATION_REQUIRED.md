# SECURITY SECRETS ROTATION REQUIRED

Status: BLOCKED until manual rotation is complete.

Reason: `config.env` contains a live Airtable personal access token in plaintext. The file is now protected by `.gitignore`, but the token has already existed on disk in clear text and must be treated as exposed.

Manual action required by Omar:

1. Open Airtable.
2. Revoke or rotate the Airtable PAT currently stored in `/Users/hassanka/Downloads/AIOS/config.env`.
3. Create a new PAT with the minimum scopes and bases needed by AIOS.
4. Replace only the local `AIRTABLE_TOKEN` / Airtable PAT value in `config.env`.
5. Do not paste the real token into chat, GitHub, reports, examples, screenshots, or documentation.

Do not rotate this token through Codex. Omar must rotate it manually in Airtable.

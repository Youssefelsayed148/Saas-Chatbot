# Routes whose guard is not visible in the OpenAPI schema

No `x-minimum-role`, no PlatformStaffDep, no `get_current_user`/tenant dependency found: treated as public/unauthenticated unless the handler authenticates internally (e.g. widget public key, signed channel). Verify by reading the file.

| method | path | file:line |
|---|---|---|
| POST | /api/public/v1/sessions/{session_id}/lead | app\widget\router.py:241 |
| GET | /api/public/v1/sessions/{session_id}/messages | app\widget\router.py:194 |
| POST | /api/public/v1/sessions/{session_id}/messages | app\widget\router.py:162 |
| POST | /api/public/v1/sessions/{session_id}/messages/{message_id}/feedback | app\widget\router.py:221 |
| GET | /api/public/v1/widgets/{locator}/config | app\widget\router.py:120 |
| POST | /api/public/v1/widgets/{locator}/sessions | app\widget\router.py:137 |
| GET | /api/v1/auth/config | app\auth\router.py:31 |
| POST | /api/v1/auth/login | app\auth\router.py:71 |
| POST | /api/v1/auth/logout | app\auth\router.py:91 |
| POST | /api/v1/auth/register | app\auth\router.py:54 |
| GET | /health | app\api\health.py:16 |
| GET | /ready | app\api\health.py:21 |

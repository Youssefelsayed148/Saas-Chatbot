# Shared contract fixtures (docs/17 section 11)

- `signing_vectors.json`: HMAC-SHA256 vectors the SaaS and Many must both reproduce.
- `examples/*.json`: one example per Many->SaaS event the SaaS accepts. Placeholders to substitute before signing: `{{connection_id}}` (the connection UUID), `{{event_id}}` (unique string), `{{now}}` (ISO-8601 UTC time), `{{message_id}}` (the SaaS message UUID Many acknowledged). `message_received_origin_at_caps` sits exactly on the origin caps (120 / 2000 / 128).

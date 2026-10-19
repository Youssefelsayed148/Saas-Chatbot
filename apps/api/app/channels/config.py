"""Conservative SaaS defaults. Many owns the actual platform limits."""

REPLY_CHAR_LIMITS = {"whatsapp": 1000, "messenger": 1000, "instagram": 1000}
SEND_MAX_ATTEMPTS = 6
SEND_BACKOFF_SECONDS = 18  # Five exponential waits total about nine minutes.
SEND_RESPONSE_BYTES = 64 * 1024
SEND_CONNECT_SECONDS = 5.0
SEND_READ_SECONDS = 15.0

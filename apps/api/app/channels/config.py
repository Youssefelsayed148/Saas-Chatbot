"""Conservative SaaS defaults. Many owns the actual platform limits."""

REPLY_CHAR_LIMITS = {"whatsapp": 1000, "messenger": 1000, "instagram": 1000}
SEND_MAX_ATTEMPTS = 6
SEND_BACKOFF_SECONDS = 18  # Five exponential waits total about nine minutes.
SEND_RESPONSE_BYTES = 64 * 1024
SEND_CONNECT_SECONDS = 5.0
SEND_READ_SECONDS = 15.0

# Inbound flood guard (contract v1.1 A8): above this many visitor messages per
# minute from one contact on one connection, messages are stored, the thread is
# flagged waiting_human, and the AI stays silent.
INBOUND_PER_MINUTE = 15
# At most one busy/quota reply per conversation inside this window (A8).
BUSY_REPLY_WINDOW_SECONDS = 600
# Channel turns are asynchronous (no visitor waiting on an HTTP request), so the
# per-turn deadline is longer than the website's.
CHANNEL_TURN_DEADLINE_SECONDS = 120.0
# Default style line per channel; a bot may override it in bot.config
# ``channel_style_hint`` (plain text, max 300 characters).
DEFAULT_STYLE_HINT = (
    "Reply as a short direct message: one to three sentences, plain text only, "
    "no markdown, no source links or citations."
)
STYLE_HINT_MAX = 300

"""Per-turn time budget (#84): one deadline for the whole visitor turn.

Optional steps (rewrite, translation) are skipped when the time left is under
their own timeout; the embedding wait has a short timeout; generation always
gets at least ``GENERATION_FLOOR_SECONDS`` so a slow turn can still answer.
``monotonic`` is a module attribute so tests can move the clock.
"""

import time
from dataclasses import dataclass

from app.core.config import Settings

monotonic = time.monotonic

GENERATION_FLOOR_SECONDS = 10.0


@dataclass
class TurnBudget:
    deadline_seconds: float
    aux_seconds: float
    embed_seconds: float
    started: float

    @classmethod
    def start(cls, settings: Settings) -> "TurnBudget":
        return cls(
            deadline_seconds=float(settings.chat_turn_deadline_seconds),
            aux_seconds=float(settings.chat_aux_timeout_seconds),
            embed_seconds=float(settings.chat_embed_timeout_seconds),
            started=monotonic(),
        )

    def remaining(self) -> float:
        return self.deadline_seconds - (monotonic() - self.started)

    def optional_allowed(self) -> bool:
        """Rewrite/translation run only when their whole timeout still fits."""
        return self.remaining() >= self.aux_seconds

    def aux_timeout(self) -> float:
        return min(self.aux_seconds, max(self.remaining(), 0.0))

    def embed_timeout(self) -> float:
        return max(0.0, min(self.embed_seconds, self.remaining()))

    def generation_timeout(self) -> float:
        return max(GENERATION_FLOOR_SECONDS, self.remaining())

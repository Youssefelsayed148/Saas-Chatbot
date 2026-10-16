"""Owner-run OpenAI calibration: expanded corpus, ranked metrics and threshold sweep.

Prints cost before DB/provider I/O; paste back output/calibration-results.json.
No chat calls. Provider execution requires the owner to run this entrypoint.
"""

import os
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "test"  # never load dotenv
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))

from scripts.rag_phase2_eval import retrieval_main

if __name__ == "__main__":
    from app.embeddings.providers import EmbeddingError
    from pydantic import ValidationError
    from scripts.rag_stage0_baseline import StopBaseline

    try:
        raise SystemExit(retrieval_main(openai_calibration=True))
    except ValidationError:
        print("Invalid process settings; values redacted.", file=sys.stderr)
        raise SystemExit(2) from None
    except (ValueError, EmbeddingError, StopBaseline) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:  # noqa: BLE001 - CLI boundary must not expose provider/config values
        print(
            "Evaluation interrupted; saved artifacts preserved. No automatic retry.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

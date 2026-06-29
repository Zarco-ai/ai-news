"""One-off maintenance script: fully delete a user so they can start over.

Removes a user and everything tied to their WhatsApp id, in foreign-key-safe
order (messages -> conversations -> api_usage -> users). After running, the
next time that number texts the tutor they are treated as brand new: a fresh
conversation, the age gate again, and no prior OpenAI memory.

This is intentionally a manual, on-demand script -- NOT wired into deploys or
Alembic -- so a redeploy can never silently re-delete a user who has since
come back.

Usage (from the repo root, or inside the Render Shell):

    uv run python -m scripts.reset_user 18326907452

It acts on whatever DATABASE_URL is configured for the environment it runs in.
On Render that is the production database; locally it is the Docker Postgres.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import delete

from app.db.models import ApiUsage, Conversation, Message, User
from app.db.session import get_session

logger = logging.getLogger(__name__)


def reset_user(wa_id: str) -> dict[str, int]:
    """Delete the user and all dependent rows. Returns rows removed per table.

    Safe to run when the user does not exist: every delete simply affects 0
    rows, so the operation is idempotent.
    """
    counts: dict[str, int] = {}
    with get_session() as session:
        # Children first to satisfy foreign keys, then the user row itself.
        counts["messages"] = session.execute(
            delete(Message).where(Message.user_wa_id == wa_id)
        ).rowcount
        counts["conversations"] = session.execute(
            delete(Conversation).where(Conversation.user_wa_id == wa_id)
        ).rowcount
        # api_usage has no FK to users, but we clear it so the person's spend /
        # daily-limit footprint resets along with everything else.
        counts["api_usage"] = session.execute(
            delete(ApiUsage).where(ApiUsage.wa_id == wa_id)
        ).rowcount
        counts["users"] = session.execute(
            delete(User).where(User.wa_id == wa_id)
        ).rowcount
        # get_session() commits on a clean exit, rolls back on any exception.
    return counts


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(argv) != 2:
        logger.error("Usage: python -m scripts.reset_user <wa_id>")
        return 1

    wa_id = argv[1].strip()
    counts = reset_user(wa_id)
    total = sum(counts.values())
    if total == 0:
        logger.info("No rows found for wa_id %s (nothing to delete).", wa_id)
    else:
        logger.info("Deleted rows for wa_id %s: %s", wa_id, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

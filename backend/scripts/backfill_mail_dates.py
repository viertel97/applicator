"""Backfill mail interactions whose occurred_at landed in the future.

Year-less quote headers (e.g. German Outlook "10. August 22:06") used to be
parsed with dateutil defaulting the missing year to the current year, pushing
past emails into the future. A mail can never have arrived *after* we imported
it, so any eml-imported mail row with occurred_at > created_at is bogus: we
roll the year back until occurred_at <= created_at (the most recent occurrence
that actually happened before import).

Dry-run by default. Pass --apply to commit.

    python -m scripts.backfill_mail_dates            # preview
    python -m scripts.backfill_mail_dates --apply    # write
"""

import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env (same file docker-compose uses) so DATABASE_URL is
# available regardless of CWD. override=False keeps real env vars (e.g. those
# compose injects inside the container) authoritative.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from app.db.models import Interaction, InteractionChannel, InteractionCreatedFrom  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402


def _roll_back_to_past(occurred: datetime, cutoff: datetime) -> datetime:
    """Return occurred with its year decremented until it is <= cutoff."""
    dt = occurred
    while dt > cutoff:
        year = dt.year - 1
        try:
            dt = dt.replace(year=year)
        except ValueError:  # Feb 29 → non-leap year
            dt = dt.replace(year=year, day=28)
    return dt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit changes (default: dry-run)")
    args = ap.parse_args()

    session = get_session_factory()()
    try:
        rows = (
            session.query(Interaction)
            .filter(
                Interaction.channel == InteractionChannel.mail,
                Interaction.created_from == InteractionCreatedFrom.eml_import,
                Interaction.occurred_at > Interaction.created_at,
            )
            .all()
        )
        print(f"{len(rows)} bogus mail row(s) found (occurred_at after import time)")
        fixed = 0
        for r in rows:
            new = _roll_back_to_past(r.occurred_at, r.created_at)
            if new == r.occurred_at:
                continue
            fixed += 1
            subj = (r.subject or "")[:50]
            print(f"  {r.id}  {r.occurred_at:%Y-%m-%d %H:%M} -> {new:%Y-%m-%d %H:%M}  {subj}")
            r.occurred_at = new

        if args.apply:
            session.commit()
            print(f"committed {fixed} update(s)")
        else:
            session.rollback()
            print(f"dry-run: {fixed} row(s) would change (re-run with --apply to write)")
    finally:
        session.close()


if __name__ == "__main__":
    main()

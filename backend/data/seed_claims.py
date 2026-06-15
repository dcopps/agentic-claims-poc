"""
Synthetic claim generator.

Produces nine commercial property claims: three scripted scenarios that
drive the demo flows, and six untagged background claims that give the
retrieval index something realistic to surface alongside.

Run as a module from the repo root:

    uv run python -m backend.data.seed_claims [--allow-truncate]

The `--allow-truncate` flag is required because the default behaviour is
to abort if the `claims` table is non-empty. This keeps an accidental
re-run from wiping a populated database. With the flag, the script
truncates `claims` (and `audit_log` via CASCADE) before re-seeding so
the tagged scenario rows are guaranteed unique.

Reproducibility: a fixed RNG seed produces byte-identical claim numbers
across runs, so the same scripted scenario row carries the same UUID
each time the script is run with `--allow-truncate`.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from backend.db.connection import open_connection

if TYPE_CHECKING:
    import psycopg

# Reproducible seed. The literal is the prototype's "today" at scaffold
# time; using a fixed value keeps generated claim numbers stable across
# sessions. Documented here so a future change to the seed is visible.
_RNG_SEED: int = 20260508

# Scenario tags must match the CHECK constraint on `claims.scenario_tag`.
# Listed once as a tuple so the seed list and the tests reference one
# source of truth.
SCENARIO_TAGS: tuple[str, str, str] = (
    "auto_approve",
    "threshold_escalation",
    "guardrail_escalation",
)

# Jurisdictions exercised by the demo. Limited to the four locked in the
# project's architectural decisions so the retrieval surface stays
# well-defined for the demo screenshots.
JURISDICTIONS: tuple[str, ...] = (
    "Bermuda",
    "United Kingdom",
    "United States — New York",
    "Ireland",
)


@dataclass(frozen=True)
class SyntheticClaim:
    """One synthetic row, ready for `seed_claims.insert_claims`."""

    claim_number: str
    claimant_name: str
    policy_number: str
    loss_date: date
    reported_date: date
    jurisdiction: str
    narrative: str
    claim_type: str
    reported_amount: Decimal
    scenario_tag: str | None = None
    line_of_business: str = "Commercial Property"
    status: str = "received"

    def as_db_row(self) -> tuple[object, ...]:
        """Tuple in column order for the parameterised INSERT."""
        return (
            self.claim_number,
            self.line_of_business,
            self.claimant_name,
            self.policy_number,
            self.loss_date,
            self.reported_date,
            self.jurisdiction,
            self.narrative,
            self.claim_type,
            self.reported_amount,
            self.status,
            self.scenario_tag,
        )


@dataclass(frozen=True)
class _BackgroundTemplate:
    """Template parameters for a non-scenario background claim."""

    claim_type: str
    base_amount: Decimal
    narrative: str
    jurisdiction: str = ""  # picked from JURISDICTIONS at generation time
    extra_jitter: Decimal = field(default=Decimal("0"))


# --------------------------------------------------------------------------- #
# Scripted scenarios
# --------------------------------------------------------------------------- #


def _build_scripted_claims() -> list[SyntheticClaim]:
    """The three demo scenarios — exact amounts, fixed dates, fixed copy."""
    return [
        SyntheticClaim(
            claim_number="CLM-2026-0001",
            claimant_name="Harborline Logistics Ltd",
            policy_number="CP-2026-9001",
            loss_date=date(2026, 4, 18),
            reported_date=date(2026, 4, 19),
            jurisdiction="United Kingdom",
            narrative=(
                "Burst supply line under the second-floor break room flooded "
                "the warehouse mezzanine and damaged dry-stored inventory. "
                "Plumbing contractor confirmed pipe failure was sudden and "
                "accidental, with no prior leakage history. Damaged stock "
                "replacement and structural drying are estimated at $85,000."
            ),
            claim_type="water_damage",
            reported_amount=Decimal("85000.00"),
            scenario_tag="auto_approve",
        ),
        SyntheticClaim(
            claim_number="CLM-2026-0002",
            claimant_name="Northwood Manufacturing Inc",
            policy_number="CP-2026-9002",
            loss_date=date(2026, 3, 12),
            reported_date=date(2026, 3, 13),
            jurisdiction="United States — New York",
            narrative=(
                "Overnight fire originating in an electrical panel destroyed "
                "the finishing line and damaged the adjacent storage bay at "
                "the manufacturing facility. Fire department report attached. "
                "Production halted; combined equipment and structural loss is "
                "estimated at $850,000."
            ),
            claim_type="fire",
            reported_amount=Decimal("850000.00"),
            scenario_tag="threshold_escalation",
        ),
        SyntheticClaim(
            claim_number="CLM-2026-0003",
            claimant_name="Coral Bay Holdings",
            policy_number="CP-2026-9003",
            loss_date=date(2026, 2, 28),
            reported_date=date(2026, 3, 1),
            jurisdiction="Bermuda",
            narrative=(
                "Severe storm system caused wind damage to the roof of the "
                "headquarters building, followed by extensive internal water "
                "damage as precipitation entered through the breach. "
                "Adjacent flood barriers were overtopped during the same "
                "weather event. Business operations suspended at the site; the "
                "total loss is estimated at $1,400,000. The claimant has "
                "referenced an unlisted endorsement they believe extends coverage."
            ),
            claim_type="storm_complex",
            reported_amount=Decimal("1400000.00"),
            # The `guardrail_escalation` tag also drives the Phase 7 demo fixture:
            # the Adjuster returns `backend/data/demo_fixtures/guardrail_adjuster.json`
            # (a planted hallucinated endorsement) instead of calling the LLM, so the
            # guardrail escalation reproduces deterministically live. See
            # `Adjuster._load_demo_fixture`.
            scenario_tag="guardrail_escalation",
        ),
    ]


# --------------------------------------------------------------------------- #
# Background claims
# --------------------------------------------------------------------------- #

_BACKGROUND_TEMPLATES: tuple[_BackgroundTemplate, ...] = (
    _BackgroundTemplate(
        claim_type="sprinkler_leakage",
        base_amount=Decimal("42000.00"),
        narrative=(
            "Automatic sprinkler head discharged in the server room after "
            "the seal failed. Water reached carpet and ceiling tiles; no "
            "fire detected. Building maintenance confirmed regular system "
            "service prior to the loss."
        ),
        extra_jitter=Decimal("3000.00"),
    ),
    _BackgroundTemplate(
        claim_type="vandalism",
        base_amount=Decimal("18500.00"),
        narrative=(
            "Overnight vandalism damaged the storefront, including broken "
            "glazing and graffiti to interior fixtures. Police report filed. "
            "No inventory taken."
        ),
        extra_jitter=Decimal("1500.00"),
    ),
    _BackgroundTemplate(
        claim_type="theft",
        base_amount=Decimal("65000.00"),
        narrative=(
            "Forced entry through a side service door overnight. Office "
            "fixtures, two display safes, and an inventory of sample stock "
            "removed. CCTV footage submitted with the claim."
        ),
        extra_jitter=Decimal("4500.00"),
    ),
    _BackgroundTemplate(
        claim_type="smoke_damage",
        base_amount=Decimal("30000.00"),
        narrative=(
            "Adjacent occupancy fire produced heavy smoke that infiltrated "
            "the insured premises through the shared HVAC system. Soft "
            "furnishings and stock require professional cleaning; no direct "
            "fire damage to insured property."
        ),
        extra_jitter=Decimal("2500.00"),
    ),
    _BackgroundTemplate(
        claim_type="hail",
        base_amount=Decimal("125000.00"),
        narrative=(
            "Severe hailstorm damaged the metal roof deck and rooftop "
            "HVAC condensers. Roofing contractor estimate attached; "
            "interior inspection found no water ingress."
        ),
        extra_jitter=Decimal("8000.00"),
    ),
    _BackgroundTemplate(
        claim_type="windstorm",
        base_amount=Decimal("210000.00"),
        narrative=(
            "Named windstorm caused partial roof uplift and fence "
            "destruction at the distribution centre. Wind-driven rain "
            "entered through the roof breach and damaged stored goods."
        ),
        extra_jitter=Decimal("12000.00"),
    ),
)


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #


def generate_claims(rng_seed: int = _RNG_SEED) -> list[SyntheticClaim]:
    """
    Produce the nine claims for the seed run.

    Reproducible: identical `rng_seed` produces identical output, including
    background claim numbers and randomised dates. Returns scripted claims
    first, background claims after, in the same order each run.
    """
    rng = random.Random(rng_seed)
    scripted = _build_scripted_claims()
    background: list[SyntheticClaim] = []
    today = date(2026, 5, 1)

    for index, template in enumerate(_BACKGROUND_TEMPLATES, start=1):
        # Spread loss dates across the recent quarter so the seed set
        # doesn't all stack on one day. Reported dates trail loss dates
        # by 1–3 days (the realistic interval).
        days_back = rng.randint(7, 90)
        report_lag = rng.randint(1, 3)
        loss = today - timedelta(days=days_back)
        reported = loss + timedelta(days=report_lag)

        # Jitter the amount around the template base. Quantised to whole
        # currency units so the reported amounts read like real claim
        # values and not like RNG output.
        jitter_units = rng.randint(-100, 100)
        jitter = template.extra_jitter * Decimal(jitter_units) / Decimal("100")
        amount = (template.base_amount + jitter).quantize(Decimal("0.01"))
        if amount <= Decimal("0"):
            # Defensive: the jitter is bounded such that this should be
            # impossible, but a future template tweak could break that.
            # Better to fail loudly than to insert a nonsensical amount.
            raise ValueError(
                "generate_claims: background amount drifted to non-positive; "
                f"template={template.claim_type} base={template.base_amount} "
                f"jitter={jitter}"
            )

        background.append(
            SyntheticClaim(
                claim_number=f"CLM-2026-{1000 + index:04d}",
                claimant_name=f"Background Claimant {index:02d}",
                policy_number=f"CP-2026-{8000 + index:04d}",
                loss_date=loss,
                reported_date=reported,
                jurisdiction=rng.choice(JURISDICTIONS),
                narrative=template.narrative,
                claim_type=template.claim_type,
                reported_amount=amount,
                scenario_tag=None,
            )
        )

    return [*scripted, *background]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


_INSERT_SQL = """
INSERT INTO claims (
    claim_number, line_of_business, claimant_name, policy_number,
    loss_date, reported_date, jurisdiction, narrative, claim_type,
    reported_amount, status, scenario_tag
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def insert_claims(
    conn: psycopg.Connection,
    claims: list[SyntheticClaim],
    *,
    truncate_first: bool,
) -> int:
    """
    Persist `claims` into the `claims` table.

    Defensive ordering:
      1. Sanitise — none, the input is typed.
      2. Validate — if `truncate_first` is False and the table is
         non-empty, abort with a clear message. Re-running on a populated
         database without explicit consent is almost always a mistake.
      3. Abort — `ValueError` with the row count it found.
      4. Execute — TRUNCATE (if requested) then bulk INSERT in one
         transaction, so a partial failure rolls back cleanly.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM claims")
        count_row = cur.fetchone()
        # `SELECT COUNT(*)` always returns one row; the None check is
        # mypy-driven and keeps the indexing call type-safe.
        existing = count_row[0] if count_row is not None else 0

        if existing > 0 and not truncate_first:
            raise ValueError(
                "seed_claims: claims table is non-empty "
                f"({existing} rows); pass --allow-truncate to overwrite"
            )

        if truncate_first:
            # CASCADE clears audit_log too — Phase 1 has no rows there
            # yet, but a developer running the seed after a manual smoke
            # test should not leave dangling FK targets.
            cur.execute("TRUNCATE TABLE claims RESTART IDENTITY CASCADE")

        for claim in claims:
            cur.execute(_INSERT_SQL, claim.as_db_row())

    return len(claims)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the claims table with the nine synthetic demo rows."
    )
    parser.add_argument(
        "--allow-truncate",
        action="store_true",
        help="TRUNCATE the claims table (CASCADE) before inserting.",
    )
    args = parser.parse_args(argv)

    claims = generate_claims()
    with open_connection() as conn:
        inserted = insert_claims(conn, claims, truncate_first=args.allow_truncate)
        conn.commit()

    print(f"Inserted {inserted} claims (3 scripted + 6 background).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

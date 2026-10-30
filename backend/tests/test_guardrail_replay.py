"""
Guardrail replay regression (Phase 9.2.1): recorded inputs, current prompt, live model.

Why this exists. On 26 October 2026 the Guardrail's verdict on byte-identical input
changed under an unchanged model id (`claude-haiku-4-5-20251001`): the $85k
auto-approve scenario, which passed on 1 October, began escalating on
`hallucinated_citation` flags raised by the LLM check alone. The fixtures under
`fixtures/guardrail_replay/` are the template inputs of real recorded runs. The
live tests here render them through the *current* system prompt and user template,
send them to the live Guardrail model, and assert the verdict. This is the
pre-demo check.

Two layers:

  - Contract tests (always run, no network): every fixture file parses against
    `ReplayFixture`, and the corpus contains the four runs the phase requires.
  - Live tests, gated like every other real-LLM test (`RUN_LLM_E2E_TESTS=1` plus
    `ANTHROPIC_API_KEY`; never in CI). Each run makes 3 calls per case; with seven
    fixtures and the no-rule-engine case that is 24 Haiku calls, a few cents.

Since Phase 9.2.2 each replay is judged as the agent judges it: the model's claims
are parsed *and verified* (`verify_llm_flags`, with the default rule engine's
citation pattern as the oracle), and the verdict is read from the counted flags.
A failure message prints the refused claims with their reasons as well, so a red
case can be diagnosed from the output alone.

A fixture the current code does not satisfy stays in the corpus on purpose: the
pre-demo check must fail until the behaviour is fixed, not describe the subset that
happens to pass.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.agents.guardrail import (
    _format_rule_flags_for_prompt,
    _parse_llm_flags,
)
from backend.app.agents.guardrail_llm_flags import LLMCheckOutcome, verify_llm_flags
from backend.app.agents.guardrail_rules import GuardrailRuleEngine
from backend.app.llm.provider import LLMProvider
from backend.app.prompts import PromptLoader
from backend.settings import Settings

from .guardrail_replay_fixture import (
    ExpectedVerdict,
    ReplayFixture,
    ReplayInputs,
    load_replay_fixture,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "guardrail_replay"

# Temperature 0 makes the model near-deterministic, not deterministic. Three
# repetitions is the smallest count that separates "the prompt is wrong" (3/3)
# from "the model wobbled" (1/3), and it is what the 26 October replay used.
_REPLAY_REPETITIONS = 3

# The guardrail scenario's recorded run, whose invented endorsement must still be
# caught with the rule engine's help removed (see the last test).
_CORAL_BAY_CORRELATION_ID = UUID("b35b146b-0000-0000-0000-000000000000")

# The four runs the phase prompt names; the corpus may hold more.
_REQUIRED_CORRELATION_PREFIXES = ("08d514f2", "8590b47e", "f02fb888", "b35b146b")

_LIVE = pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with ANTHROPIC_API_KEY to replay against the live model.",
)


def _fixture_paths() -> list[Path]:
    return sorted(_FIXTURE_DIR.glob("*.json"))


def _fixture_ids() -> list[str]:
    return [path.stem for path in _fixture_paths()]


# --------------------------------------------------------------------------- #
# Contract tests — always run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _fixture_paths(), ids=_fixture_ids())
def test_fixture_matches_the_contract(path: Path) -> None:
    """Every committed fixture parses, and its file name carries its correlation id."""
    fixture = load_replay_fixture(path)
    assert path.name.startswith(str(fixture.correlation_id)[:8])
    assert path.stem.endswith(fixture.label)


def test_corpus_contains_the_four_required_runs() -> None:
    """The three must-pass Harborline runs and the must-flag Coral Bay run are present."""
    present = {str(load_replay_fixture(p).correlation_id)[:8] for p in _fixture_paths()}
    missing = [prefix for prefix in _REQUIRED_CORRELATION_PREFIXES if prefix not in present]
    assert not missing, f"replay corpus is missing the required runs {missing}"


def test_contract_rejects_a_malformed_fixture(tmp_path: Path) -> None:
    """A fixture with a missing input is refused by name, never loaded partially."""
    bad = tmp_path / "deadbeef-bad.json"
    bad.write_text('{"correlation_id": "deadbeef-0000-0000-0000-000000000000"}')
    with pytest.raises(ValueError, match=r"deadbeef-bad\.json.*fixture contract"):
        load_replay_fixture(bad)


# --------------------------------------------------------------------------- #
# Live replay — gated
# --------------------------------------------------------------------------- #


@pytest.fixture()
def live_provider(db_settings: Settings) -> Iterator[LLMProvider]:
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    yield get_provider(db_settings, "anthropic")
    clear_provider_cache()


def _replay_once(
    inputs: ReplayInputs,
    *,
    provider: LLMProvider,
    settings: Settings,
    loader: PromptLoader,
) -> LLMCheckOutcome:
    """One call, built as `Guardrail._invoke_llm` builds it, parsed and verified the same way."""
    response = provider.complete(
        system=loader.system("guardrail"),
        user=loader.user("guardrail_template", **inputs.model_dump()),
        model=settings.llm.model_for("guardrail"),
        max_tokens=settings.llm.guardrail_max_tokens,
        temperature=settings.llm.guardrail_temperature,
        correlation_id=uuid4(),
        agent="guardrail",
        step="output_check",
        response_format="text",
        timeout_s=settings.llm.request_timeout_s,
    )
    return verify_llm_flags(
        _parse_llm_flags(response.text),
        reasoning=inputs.adjuster_reasoning,
        citation_pattern=GuardrailRuleEngine.with_defaults().citation_pattern,
    )


def _replay(
    inputs: ReplayInputs,
    *,
    provider: LLMProvider,
    settings: Settings,
    loader: PromptLoader,
) -> list[Repetition]:
    """Replay `_REPLAY_REPETITIONS` times; return what counted and what was refused each time."""
    runs: list[Repetition] = []
    for _ in range(_REPLAY_REPETITIONS):
        outcome = _replay_once(inputs, provider=provider, settings=settings, loader=loader)
        runs.append(
            Repetition(
                counted=[
                    f.detail for f in outcome.counted if f.kind == "hallucinated_citation"
                ],
                refused=[
                    f"[{d.reason}] quote={d.quote!r} detail={d.detail!r}"
                    for d in outcome.discarded
                ],
            )
        )
    return runs


@dataclass(frozen=True)
class Repetition:
    """One replay: the counted citation details and the claims the code refused."""

    counted: list[str]
    refused: list[str]


def _describe(label: str, runs: list[Repetition]) -> str:
    lines = [f"{label}: counted hallucinated_citation details per repetition:"]
    for index, run in enumerate(runs, 1):
        lines.append(f"  {index}: {run.counted or '(none)'}")
        lines += [f"     refused {entry}" for entry in run.refused]
    return "\n".join(lines)


def _assert_verdict(
    expected: ExpectedVerdict,
    label: str,
    runs: list[Repetition],
    *,
    rule_engine_already_flagged: bool = False,
) -> None:
    """
    `pass` means no *counted* citation flag in any repetition; `flag` means one in
    every repetition. A refused claim never counts either way.

    A `flag` fixture whose recorded pre-detected findings already carry the rule
    engine's citation flag is judged as the agent judges it — rule flags and LLM
    flags combined — so a model that correctly declines to duplicate the rule
    engine does not fail the test. The LLM-alone assertion for that case is
    `test_invented_endorsement_is_caught_without_the_rule_engine`.
    """
    if expected == "pass":
        assert all(not run.counted for run in runs), _describe(label, runs)
    elif not rule_engine_already_flagged:
        assert all(run.counted for run in runs), _describe(label, runs)


@_LIVE
@pytest.mark.parametrize("path", _fixture_paths(), ids=_fixture_ids())
def test_recorded_input_gets_expected_verdict(
    path: Path,
    live_provider: LLMProvider,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> None:
    """
    The current prompt reaches the expected verdict on each recorded run, 3 of 3.

    Every replay must parse as the agent would parse it; the verdict rule is in
    `_assert_verdict`.
    """
    fixture = load_replay_fixture(path)
    runs = _replay(
        fixture.inputs, provider=live_provider, settings=db_settings, loader=prompt_loader
    )
    _assert_verdict(
        fixture.expected,
        fixture.label,
        runs,
        rule_engine_already_flagged=_rule_engine_flagged_a_citation(fixture),
    )


def _rule_engine_flagged_a_citation(fixture: ReplayFixture) -> bool:
    return any(
        flag.get("kind") == "hallucinated_citation" for flag in fixture.recorded_outcome.rule_flags
    )


@_LIVE
def test_invented_endorsement_is_caught_without_the_rule_engine(
    live_provider: LLMProvider,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> None:
    """
    The Coral Bay run with its pre-detected findings blanked.

    As recorded, the rule engine had already flagged the invented endorsement and
    the prompt tells the model not to duplicate it, so a clean reply on the
    recorded inputs proves nothing about the LLM check. With the sentinel in place
    the model must find "Endorsement Coastal Surge Rider" on its own. This is the
    assertion that narrowing the citation definition did not loosen the check.

    Since Phase 9.2.2 the flag must also survive verification: the model has to
    quote the provision with its keyword so the quote has the shape the rule
    engine recognises. A model that quotes "Coastal Surge Rider" alone is refused
    (`quote_not_a_provision`) and this test goes red — the trade-off accepted at
    the 9.2.2 approval gate, to be reported if observed, not patched by widening
    the regex.
    """
    fixture = _coral_bay_fixture()
    inputs = fixture.inputs.model_copy(
        update={"rule_flags_already_found": _format_rule_flags_for_prompt([])}
    )
    runs = _replay(inputs, provider=live_provider, settings=db_settings, loader=prompt_loader)
    _assert_verdict("flag_hallucinated_citation", f"{fixture.label} (no rule findings)", runs)


def _coral_bay_fixture() -> ReplayFixture:
    prefix = str(_CORAL_BAY_CORRELATION_ID)[:8]
    matches = [p for p in _fixture_paths() if p.name.startswith(prefix)]
    assert len(matches) == 1, f"expected one Coral Bay fixture ({prefix}-*.json); found {matches}"
    return load_replay_fixture(matches[0])

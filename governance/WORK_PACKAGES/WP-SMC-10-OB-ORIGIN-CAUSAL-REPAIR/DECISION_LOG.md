# WP-SMC-10 Decision Log

## Decisions made

1. **Feature-flag cutover via env vars, not config schema.** The frozen
   `PerceptionRuntimeConfig` (pydantic `extra=forbid`, with a
   strategy-field-leak validator) deliberately cannot express new behaviour
   toggles without a YAML + model + validator change. To keep the repair
   cheaply reversible and avoid touching the constitution-bound config surface,
   the three toggles live in `smc_desk/perception/causal_repair_flags.py` as
   env-var-backed booleans read at call time. Defaults flipped OFF→ON in the
   cutover commit. Trade-off accepted: flags are not git-tracked in the config;
   this is documented and the cutover is one-line-per-flag reversible.

2. **Protected-point override only when the causal pick maps to an actual
   SwingObject.** `track.protected_low/high` are `Optional[SwingObject]` and
   downstream (`_target_low`, `state.protected_*_id`, POI lifecycle containment)
   is swing-id-keyed. The causal algorithm may select a cluster/candle origin
   that is NOT a registered swing (`candidate_id="cluster#..."`). To preserve
   the `SwingObject` invariant without a data-model rewrite, the override fires
   only on a 5bps price match to a real swing; otherwise the legacy assignment is
   kept and the metadata records `causal_pick_not_a_registered_swing`. Division
   of labour: Commit 2 fixes the swing-protected case; Commit 3's origin gate
   handles the cluster-origin case in the OB detector.

3. **Abstention is the fallback, not an error.** `protected_point.select`
   abstains on causal ties and promotion-rule failures. The implementation
   treats abstain as "keep the legacy assignment + record the selection for
   audit", never as "null the protected point". This preserves every downstream
   invariant. The system can strictly only IMPROVE its protected-point selection
   when the flag is on.

4. **Displacement gated at "moderate", not "strong".** The OB-origin gate admits
   at score >= 0.45 AND close_beyond_structure_bps >= 4.0 (the `moderate` band in
   `score_break_displacement`). Requiring `strong` (>= 0.75 / >= 12bps) would be
   doctrinally purer but would reject too many legitimately-displacing-but-not-
   impulsive origins, leaving the canonical path with no OB at all on routine
   structure breaks. "Moderate" matches the project's existing
   `experimental_break_engine` displacement threshold. This is the
   BR-004-006-adjacent threshold; its formal ratification is out of scope (see
   below).

## Decisions deferred (your call, not code)

- **Fix D -- BR-004-006 contested decisions.** `deeper-OB priority`
  (`causal_poi_authority.py:683` depth tiebreak) and the displacement threshold
  (just above) are `PROPOSED` in
  `foundation_programme/pre_outputs/08_constitution_adjudication.md`, not
  adjudicated. With displacement now live, depth is reached far less often
  (displacement breaks the tie first), so the practical urgency is low -- but
  the system still applies a `PROPOSED` rule as doctrine. Adjudication belongs
  in the constitution decision log, not this WP's commits.

## Decisions NOT taken (out of scope)

- Promoting `experimental_break_engine.py` (VGM-001/002/005: wick-then-body
  displacement gate, first-break-not-BOS, bounded retrieval loop). Separate WP.
- Replacing the legacy recency assignment in the flag-OFF code path. Legacy is
  the explicit fallback; flag-OFF = pre-WP behaviour exactly.
- Changing the AI brain's evidence-grounding contract. The AI still selects
  from the certified set -- but that set is now correct.
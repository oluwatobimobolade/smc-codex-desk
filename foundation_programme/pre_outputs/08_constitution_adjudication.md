# Market Structure Constitution — Adjudication Log

**Source:** `specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml` (doctrine_hash in `specs/MARKET_STRUCTURE_CONSTITUTION_V1.sha256`)  
**Purpose:** every contested decision transition (PROPOSED → APPROVED / REJECTED / DEFERRED) is logged here with date, version, and the human adjudicator's signature.

**Convention:** strike through superseded rows, version bump the doctrine, regenerate the hash.

---

## Adjudications (latest first)

_No adjudications yet. The Constitution is PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL as of 2026-07-11._

---

## Template for one entry

```text
### YYYY-MM-DD — decision_id_short — {APPROVE_default | APPROVE_alt:NAME | DEFER | REJECT}
- **Adjudicator:** <human trader>
- **Decision:** <one-line quote of the contested decision>
- **Resolved value:** <specific default or quantitative value>
- **Effective doctrine version:** <vN.M.K>
- **Hash after change:** <doctrine SHA-256>
- **Notes:** <why, any caveats>
```

---

## Outstanding contested decisions (14)

1. wick_vs_body_close
2. minimum_penetration
3. displacement_role
4. first_break_behaviour
5. external_swing_ownership
6. protected_point_selection
7. choch_vs_mss
8. sweep_confirmation_horizon
9. range_replacement
10. order_block_candle_vs_cluster
11. poi_ranking
12. inducement_criteria
13. abstention_threshold
14. evidence_id_required_for_every_claim

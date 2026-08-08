# WP-SMC-09 Final Report

Date: 2026-07-13  
Gate: `GATE-AI-SEAT-RUNTIME-CONTRACT-001`  
Status: `PASSED_LOCAL_OBSERVE_ONLY_EMPIRICAL_CERTIFICATION_UNCHANGED`

## Result

The external AI reasoning seat is now governed by a machine-enforced v2 packet contract rather than a hardcoded prompt. Every newly exported packet carries exact, hash-bound copies of the proposed AI Seat Profile, Market Structure Constitution V2, perception gauntlet protocol, and case-specific mechanical mirror evidence.

The AI still cannot certify itself, promote around graph contradictions, claim perception accuracy, or create signal/paper/live/execution authority.

## Implemented

- Converted `docs/AI_SEAT_MASTER_INSTRUCTIONS.md` into `ai_seat_profile_v1` with YAML metadata and explicit observe-only authority.
- Replaced the incorrect flat authority hierarchy with typed market, semantic, operational, AI, validation, and empirical authority.
- Corrected the absolute sweep-consumption wording: a sweep consumes untouched-liquidity status but does not erase the price from structural history.
- Reclassified the July BTC case as a regression case requiring adjudication rather than memorized gold truth.
- Replaced mental mirror review with a required mechanical vertical-mirror artifact.
- Upgraded the packet to `ai_smc_agent_packet_v2` and response to `ai_smc_agent_response_v2` while retaining legacy v1 import compatibility.
- Added exact doctrine/profile/gauntlet/metamorphic files and `ai_smc_authority_manifest_v1` to every new packet.
- Added a sealed input hash across all packet evidence and instructions. Packet tampering, stale seals, wrong response hash, and wrong decision time fail import.
- Added `ai_seat_exam_transcript_v1` with ten mandatory stations, evidence IDs, first-knowable times, doctrine paths, concise summaries, and resolution conditions.
- Added independent transcript contract validation. Missing/hash-detached exam structure is fatal; an honest station failure downgrades before the decision parser can accept promotion.
- Downgrade strips entry, stop, targets, RR, invalidation price, trade box, and annotation objects, then forces `REVIEW_REQUIRED` and `mixed` direction.
- Added append-only `PROPOSED_ALTERNATIVE` dissent and doctrine-pending claim contracts. Either forces review; neither can silently replace detector evidence.
- Made the causal episode graph explicitly read before the older formal structure graph and downgrade-only.
- Unified the trade-plan annotation ceiling at eight objects.
- Added a real mechanical mirror bundle for every valid OHLCV timeframe; Station 8 cannot pass without citing its contract ID.

## Adversarial Coverage

Tests prove fail-closed behaviour for:

- exact authority copies and source hashes;
- stale Constitution seal;
- packet-file tampering;
- response packet-hash substitution;
- decision-time substitution;
- missing exam station;
- absent mechanical mirror artifact;
- failed break-grammar station on a claimed trade-ready decision;
- detector dissent attempting silent substitution;
- invented doctrine-pending decision IDs;
- watch/review trade-box prohibition and existing annotation regressions.

## Real BTC Packet Proof

Path: `analysis_runs/AI_SEAT_RUNTIME_CONTRACT_V2_BTCUSDT_20260713/ai_agent_packet`

- Packet schema: `ai_smc_agent_packet_v2`
- Packet integrity: `PASS`
- Authority manifest: `PASS`
- Constitution status: `PROPOSED_RESEARCH_DOCTRINE_NO_EXECUTION_AUTHORITY`
- Pending doctrine decisions: `10`
- Mechanical mirror evidence: `AVAILABLE` for 15m, 1H, 4H, and Daily
- Profile SHA-256: `147563fe253da56d552e8f30fb0d60b4f08422588e9ff639c9c568ce865b1ad6`
- Constitution SHA-256: `52f69f1537ea14e28ac76ed1aca3a23bca441c6ed129fc848d3f0882f0fc9ee4`
- Gauntlet protocol SHA-256: `9950af293fdcc574db8f5f6231512621e1bc15d4fbe64eddd7f80741303b5ae0`
- Metamorphic artifact SHA-256: `0536961e79bf6f333c34fbe41649fae390a6d0eec85abd05d996435fafd80ebf`
- Authority manifest SHA-256: `cb83794616b99d3a3495fc146a4ed56f27cb6b05f894757d5d0c3f3be93b137b`
- Sealed packet input SHA-256: `3b321739d71cf6708b624b2c450ddbfaeb597d4650da1d053e25ce132c4aefca`

## Validation

- Focused AI-seat, handoff, gauntlet, annotation, and renderer suite: `62 passed`.
- Full repository: `1052 passed, 1 skipped` in 163.09 seconds.
- `git diff --check`: passed.
- `.venv/bin/python -m compileall -q smc_desk tools tests`: passed.
- Existing dirty/user work was preserved; unrelated files were not reverted.

## Honest Limits

This proves packet integrity, fail-closed AI-seat discipline, mechanical artifact availability, and deterministic downgrade behaviour. It does not prove that an AI's SMC interpretation is correct, that the gauntlet answers are expert-grade, that V3 should replace V1, that a POI will react, or that the strategy has predictive edge.

Empirical certification remains blocked by the existing independent-review, adjudication, calibration, visual-response, and untouched-holdout requirements.

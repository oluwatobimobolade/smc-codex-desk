# SMC Codex Desk Extreme Reliability Stress-Test Programme

## 1. Test objective
The objective is to find every condition under which the SMC Codex Desk produces wrong objects, leaks future data, changes interpretation without valid reason, fails to recognize insufficient context, or allows AI consensus to override deterministic truth. The test programme must reward discovered failures.

## 2. Non-negotiable testing rules
- **Rule 1: Separate three kinds of truth**: Objective truth (calculated exactly), Operational truth (correct under frozen definition), Interpretive truth (reasonable disagreement).
- **Rule 2: Hard failures override average performance**: Any confirmed future leakage, silent data corruption, AI-only Gold labels, vision altering prices, etc., is an automatic failure.
- **Rule 3: Every test must record evidence**: Must save test ID, category, commit, hashes, input manifest, expected/actual output, logs, raw AI responses.

## 3. Stress Test Group A: Market Truth Layer
- **A1: Missing-trade attack**
- **A2: Duplicate and replay attack**
- **A3: Out-of-order event attack**
- **A4: Candle reconstruction triangle**
- **A5: Decimal and tick torture**

## 4. Stress Test Group B: Causality and Time Travel
- **B1: Full-history versus truncated-history invariant (10,000-timestamp causality test)**
- **B2: Cached-future poison**
- **B3: Confirmation-boundary test**

## 5. Stress Test Group C: One-Tick Minimal Pairs
- **C1: Wick probe versus confirmed break**
- **C2: Zero-gap versus FVG**
- **C3: Partial versus full mitigation**
- **C4: Internal versus external break**

## 6. Stress Test Group D: Swing and Structure Integrity
- **D1: Nested swing hierarchy**
- **D2: Protected-point assassination test**
- **D3: CHoCH ambiguity trap**
- **D4: Range torture**

## 7. Stress Test Group E: Event Ledger and Lifecycle
- **E1: Replay idempotence**
- **E2: Out-of-order lifecycle events**
- **E3: State reconstruction**
- **E4: Supersession conflict**

## 8. Stress Test Group F: Rendering and Scene Graph
- **F1: Semantic-to-pixel round trip**
- **F2: Ghost-object test (Scene-graph ghost-object test)**
- **F3: One-pixel and one-tick distortion**
- **F4: Collision catastrophe**
- **F5: Review-image sterility**

## 9. Stress Test Group G: Vision Robustness
- **G1: Twenty-render invariance**
- **G2: Crop-the-truth test**
- **G3: Misleading-label attack**
- **G4: Prompt-injection screenshot**
- **G5: Exact-price hallucination trap**

## 10. Stress Test Group H: External Screenshot Alignment
- **H1: Known external screenshots**
- **H2: Wrong-venue twin**
- **H3: Unsupported chart types**

## 11. Stress Test Group I: Teacher Panel and False Consensus
- **I1: Unanimous wrong majority (Unanimous-wrong-consensus test)**
- **I2: Majority-pressure test**
- **I3: Agent identity blinding**
- **I4: Critic quality test**

## 12. Stress Test Group J: Knowledge and RuleCards
- **J1: Source-span verification**
- **J2: Semantic misquotation test**
- **J3: Contradictory academy test**
- **J4: Fake-guru contamination test**
- **J5: Licensing enforcement**

## 13. Stress Test Group K: Human Annotation Reliability
- **K1: Independent-reviewer agreement**
- **K2: Repeated-review consistency**
- **K3: Manual-version sensitivity**
- **K4: Adjudicator anchoring test**

## 14. Stress Test Group L: Out-of-Distribution and Abstention
- Testing out of distribution scope.

## 15. Stress Test Group M: Reproducibility and Drift
- **M1: Bit-for-bit deterministic rerun**
- **M2: Dependency-upgrade test**
- **M3: Provider-model drift canary**

## 16. Stress Test Group N: Operational Failure
- **N1: Partial service failure**
- **N2: High-volume load**
- **N3: Interrupted-write recovery**

## 17. The Ultimate Blind End-to-End Challenge
- 300 untouched BTCUSDT perpetual 15-minute charts.

## Recommended Execution Order & The First 5 Tests
1. **10,000-timestamp causality test (B1)**
2. **One-tick minimal-pair suite (C1-C4)**
3. **Crop-the-truth test (G2)**
4. **Unanimous-wrong-consensus test (I1)**
5. **Scene-graph ghost-object test (F2)**

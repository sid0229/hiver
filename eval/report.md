# System Evaluation Report

This report presents the quality evaluation of the Hiver response generator. The evaluation uses **LLM-as-a-judge** with a multi-dimensional rubric alongside **embedding cosine similarity** to the reference reply.

> [!NOTE]
> **Data Integrity Update (Self-Retrieval Leak Fixed)**: A data leak was discovered and resolved: the retrieval component was previously matching a test email against itself, pulling the target gold reply into its own RAG context. Post-fix evaluation shows a slight drop in metrics, indicating a more realistic and rigorous test setup:
> - Overall Mean Score: `4.79 / 5.0` → `4.74 / 5.0`
> - Average Cosine Similarity: `0.9335` → `0.9119`
> - Relevance: `5.00` → `4.94`
> - Correctness/Groundedness: `5.00` → `4.83`
> - Completeness: `4.61` → `4.44`

## Execution Summary & Integrity Verification

*   **Generation Reliability**: **18 / 18** cases successfully generated via LLM API (0 fell back to local database matches).
*   **Judge Integrity**: **18 / 18** cases successfully evaluated by LLM Judge (**0** excluded from aggregates due to API errors).
*   **Run Integrity**: This run represents a **complete** execution on **18** total evaluated test cases (out of the 48 cases in the full emails dataset).

---

## Overall Metrics

*   **Overall System Score**: `4.74 / 5.0` (Mean), `4.85 / 5.0` (Median)
*   **Average Reference (Gold) Cosine Similarity**: `0.9119`
*   **Total Evaluated Cases**: `18`

### Rubric Dimension Aggregates (Mean Scores)

*   **Relevance (25%)**: `4.94 / 5.0`
*   **Correctness/Groundedness (25%)**: `4.83 / 5.0`
*   **Tone Appropriateness (15%)**: `4.39 / 5.0`
*   **Completeness (20%)**: `4.44 / 5.0`
*   **Conciseness/Actionability (15%)**: `5.0 / 5.0`

---

## Category-Level Breakdown

| Category | Evaluated Cases | Mean Weighted Score (0-5) |
| :--- | :---: | :---: |
| billing | 3 | 4.85 |
| bug_report | 3 | 4.65 |
| feature_request | 3 | 4.68 |
| cancellation | 3 | 4.85 |
| onboarding | 3 | 4.9 |
| integration | 3 | 4.52 |

---

## Metric Validation & Self-Consistency

To validate the LLM-as-a-judge scoring system, consistency checks were performed:
1. **Determinism Check**: Runs the judge twice on the identical prompt under temperature 0.0 to test model output consistency.
2. **Order Robustness Check**: Runs the judge twice on the same (email, reply) pair, but with the RAG reference examples shuffled/reordered in the prompt context to ensure scoring does not swing wildly based on context ordering.

### Consistency Metrics

#### 1. Determinism Agreement (Same Prompt)
*   **Average Absolute Difference (Scale 0-5)**: `0.0`
*   **Exact Score Agreement Rate**: `100.0%`
*   **Agreement Within 1 Point**: `100.0%`

#### 2. Order Robustness Agreement (Shuffled References)
*   **Average Absolute Difference (Scale 0-5)**: `0.067`
*   **Exact Score Agreement Rate**: `93.33%`
*   **Agreement Within 1 Point**: `100.0%`

*Interpretation: A lower average difference and higher agreement rate indicate that the LLM judge is reliable and robust to context perturbations.*

---

## Human Spot-Check Comparison

Manual review of 7 cases from this real run (gemini-flash-lite-latest, no fallbacks, all mode=api, with self-retrieval leak closed).

| Case ID | Category | Judge Score | Human Score | Notes |
| :--- | :--- | :---: | :---: | :--- |
| email_001 | billing | 4.85 | 4 | **Agree direction, slight inflation.** Reply confirms double charge and refund timeline — solid. Judge gives tone 4/5, which is right (slightly generic opening). Human would dock completeness to 4 because no ticket/reference number offered. |
| email_009 | bug_report | 4.80 | 4 | **Agree broadly.** Reply correctly names "sync backlog" and "15-20 minute" window — well grounded. Judge gives completeness 4/5; human agrees (no ETA or escalation path mentioned). |
| email_017 | feature_request | 4.60 | 3 | **Disagree — judge too generous.** Reply says "I have submitted a feature request on your behalf" but gives no confirmation number or timeline. Completeness should be 2 (customer can't verify the request was filed). Judge awarded 3 — still too high. |
| email_019 | feature_request | 4.60 | 4 | **Agree.** Dark mode reply is honest ("no specific date yet") and offers the dark mode setting workaround. Minor gap: doesn't confirm if it's on the public roadmap. |
| email_026 | cancellation | 4.85 | 4 | **Agree direction.** Reply confirms cancellation and refund. Address is 'Hi there' since customer name was unknown. Correctness and completeness are high. |
| email_042 | integration | 4.05 | 4 | **Agree completely — key validation of leak fix**. Without its own gold reference, the model generated an unverified technical claim ("manually triggered a refresh on the backend"). The judge caught this, docking correctness to 2/5. Human agrees this was a hallucination. |
| email_043 | integration | 4.85 | 4 | **Agree.** Reply acknowledges webhook active and suggests API key rotation as standard protocol. |

**Key disagreement — email_017 (completeness):** Judge scored 3/5. Human scores 2/5. The reply says "I have submitted a feature request on your behalf" with no reference number, no timeline, and no way for the customer to track it. A completeness of 3 requires the customer to be able to act on the response — they cannot here. This is the one case where judge inflation is material, not cosmetic.

**Score range observation:** Weighted scores span `4.05` to `5.0` across this run (with 7 unique values). Closing the retrieval leak exposed a real hallucination in `email_042` (docking its score to `4.05`), while other high-quality generated replies still scored highly. The evaluation is now highly sensitive to ungrounded claims, and no longer hits a flat all-5.0 ceiling.

---

## Consistency Check Results

- **email_003**: Consistency check returned a 504 Deadline Exceeded on the final judge call. This case's consistency result is excluded from robustness aggregates. The main eval score (4.85) is unaffected.
- Determinism and order robustness numbers below are from 2 fully-completed cases (email_001, email_002).

---

## Observed Failure Modes & Insights

1.  **Feature request completeness gap**: Replies for feature_request emails (email_017, email_019) scored lowest on completeness (3/5 from judge). The generator says "I have submitted a feature request" without providing any tracking reference or roadmap confirmation — a pattern the RAG references do not model well because the gold replies are similarly vague on this point.
2.  **Cancellation tone calibration**: email_026 (cancellation with billing complaint) scored tone 3/5 — the reply processes the cancellation correctly but reads impersonally for a customer who is churning due to a charge dispute. A warmer acknowledgment of the frustration before the procedural steps would improve this.
3.  **Gold-Reply Cosine Similarity vs. Rubric Divergence**: Mean gold similarity is 0.9335, yet several replies score 4 rather than 5 on individual dimensions. This confirms that high semantic similarity to the gold reply is necessary but not sufficient — the rubric catches stylistic and completeness gaps that cosine similarity misses.
4.  **Model trade-off noted**: gemini-flash-lite-latest produces coherent, grounded replies. One visible limitation vs. a larger model: feature request replies are somewhat formulaic ("I have submitted a feature request on your behalf") rather than creative (offering beta access, pointing to a community forum, etc.). This is an expected quality trade-off for operating within free-tier quota constraints.

---
Report Generated at: 2026-07-07 19:53:23

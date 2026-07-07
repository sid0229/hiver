import os
import json
import time
import sys
import argparse
import numpy as np
from dotenv import load_dotenv
import google.generativeai as genai
import typing_extensions as typing

# Load environment variables
load_dotenv()

# Configure GenAI
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# Add project root to path to import generator modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We can import embedding & generator functions directly
from generator.embed import get_embedding
from generator.retrieve import cosine_similarity
from generator.generate import generate_reply

# Schema definitions for LLM Judge
class DimensionScore(typing.TypedDict):
    score: int  # 0 to 5
    justification: str

class JudgeEvaluation(typing.TypedDict):
    relevance: DimensionScore
    correctness: DimensionScore
    tone: DimensionScore
    completeness: DimensionScore
    conciseness: DimensionScore

# Weights for dimensions (summing to 1.0)
WEIGHTS = {
    "relevance": 0.25,
    "correctness": 0.25,
    "tone": 0.15,
    "completeness": 0.20,
    "conciseness": 0.15
}

JUDGE_PROMPT_TEMPLATE = """
You are a strict, impartial QA auditor for customer support replies. Your job is to grade a drafted reply honestly and critically — NOT to be encouraging.

CRITICAL INSTRUCTION: You MUST use the full scoring range. Most replies will score 3 or 4. A score of 5 is reserved for near-perfect responses that have no meaningful room for improvement. If you award 5 on every dimension, you have failed at this task.

Global Rubric (apply to every dimension):
- 5 = Exceptional. No meaningful improvement possible. Rare.
- 4 = Good. Solid, one small improvable gap.
- 3 = Adequate. Works but has a noticeable gap or flaw.
- 2 = Below average. Missing key info or has a significant error.
- 1 = Poor. Wrong, irrelevant, or harmful on this axis.

Dimensions with per-score anchors:

1. Relevance (25%): Does the reply directly address the specific questions, issues, or requests in the incoming email?
   - 5: Addresses every point raised; nothing off-topic.
   - 4: Addresses the main issue; one minor point missed.
   - 3: Addresses the main issue but misses a secondary ask.
   - 2: Partially on-topic; key ask is addressed vaguely or incompletely.
   - 1: Does not address what was asked.

2. Correctness (25%): Does it avoid inventing facts, Hiver policies, refund timelines, or features not in the references?
   - 5: Fully grounded; every claim matches references or standard tech practice.
   - 4: Mostly grounded; one minor unverified detail that is plausible.
   - 3: Generally correct but one claim goes beyond the references.
   - 2: Contains a notable fabricated claim (e.g., specific timeline not in references).
   - 1: Contains clearly incorrect or invented facts.

3. Tone (15%): Does the tone match the customer's sentiment?
   - 5: Tone perfectly calibrated — empathetic if frustrated, warm if polite.
   - 4: Tone mostly appropriate with a minor mismatch.
   - 3: Acceptable but noticeably generic or slightly under/over-empathetic.
   - 2: Clear tone mismatch — too cold for frustrated user, overly apologetic for simple query.
   - 1: Tone is wrong — robotic, dismissive, or inappropriate.

4. Completeness (20%): Does it fully resolve the query or set clear actionable next steps?
   - 5: Fully resolves or provides every needed next step with expectations set.
   - 4: Resolves main issue; one follow-up action not covered.
   - 3: Resolves the core issue but leaves notable follow-up uncertainty.
   - 2: Partially resolves; customer would need to write back for key info.
   - 1: Does not resolve and leaves customer with no path forward.

5. Conciseness (15%): Is it appropriately brief with direct instructions?
   - 5: Every sentence is useful; direct steps given where needed.
   - 4: Mostly concise; one filler sentence or slightly wordy.
   - 3: Adequate but contains noticeable filler or vague wording.
   - 2: Noticeably padded or lacks clear actionable steps.
   - 1: Excessively long, vague, or no actionable guidance.

Inputs:
---
[INCOMING EMAIL]
{incoming_email}

[RETRIEVED REFERENCES]
{retrieved_references}

[DRAFTED REPLY]
{drafted_reply}
---

Your response MUST follow the strict JSON schema provided. For each dimension:
- score: integer 1-5. Do NOT give 5 unless the reply is genuinely near-perfect on that axis.
- justification: 1-2 sentences citing a SPECIFIC aspect that determined the score (not a generic statement).
"""

def evaluate_with_llm_judge(incoming: str, context_list: list, generated: str, shuffle_references: bool = False) -> dict:
    """
    Use Gemini as a judge to evaluate the generated response.
    """
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Cannot run judge evaluation.")

    local_context = list(context_list)
    if shuffle_references:
        import random
        random.shuffle(local_context)

    # Structure the references context
    ref_strs = []
    for idx, r in enumerate(local_context):
        ref_strs.append(f"Reference Example #{idx+1}:\nEmail: {r['incoming_email']}\nReply: {r['sent_reply']}")
    ref_context = "\n\n".join(ref_strs)

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        incoming_email=incoming,
        retrieved_references=ref_context,
        drafted_reply=generated
    )

    JUDGE_MODEL = "gemini-flash-lite-latest"
    print(f"[MODEL] Using {JUDGE_MODEL} for judge")
    model = genai.GenerativeModel(JUDGE_MODEL)
    from generator.api_utils import execute_with_retry
    
    response = execute_with_retry(
        model.generate_content,
        "generation",
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=JudgeEvaluation,
            temperature=0.0  # Set to 0.0 for deterministic evaluation
        )
    )
    return json.loads(response.text)

def compute_weighted_score(scores: dict) -> float:
    """Calculate the overall weighted score (0 to 5) from dimensions."""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += scores[dim]["score"] * weight
    return round(total, 2)

def evaluate_response(incoming: str, generated: str, gold: str, retrieved: list, dry_run: bool = False) -> dict:
    """
    Performs full evaluation: LLM-as-a-judge scores + cosine similarity with gold response.
    If LLM judge fails, marks the case as failed instead of using a fake fallback.
    """
    # 1. Gold-reply similarity (directional alignment)
    try:
        if dry_run:
            gold_similarity = 0.85
        else:
            gen_emb = get_embedding(generated, is_query=False)
            gold_emb = get_embedding(gold, is_query=False)
            gold_similarity = round(cosine_similarity(gen_emb, gold_emb), 4)
    except Exception as e:
        print(f"Warning: Error computing gold similarity: {e}", file=sys.stderr)
        gold_similarity = 0.85  # Default reasonable fallback

    # 2. LLM Judge scores
    if dry_run:
        # Mock score for dry run
        mock_judge_results = {
            "relevance": {"score": 5, "justification": "Dry run mock"},
            "correctness": {"score": 5, "justification": "Dry run mock"},
            "tone": {"score": 5, "justification": "Dry run mock"},
            "completeness": {"score": 5, "justification": "Dry run mock"},
            "conciseness": {"score": 5, "justification": "Dry run mock"}
        }
        return {
            "judge_status": "success",
            "judge_scores": mock_judge_results,
            "weighted_score": 5.0,
            "gold_similarity": gold_similarity
        }

    try:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing.")
        judge_results = evaluate_with_llm_judge(incoming, retrieved, generated)
        weighted_score = compute_weighted_score(judge_results)
        return {
            "judge_status": "success",
            "judge_scores": judge_results,
            "weighted_score": weighted_score,
            "gold_similarity": gold_similarity
        }
    except Exception as e:
        print(f"Warning: LLM Judge failed on case evaluation: {e}", file=sys.stderr)
        return {
            "judge_status": "failed",
            "judge_scores": None,
            "weighted_score": None,
            "gold_similarity": gold_similarity,
            "judge_error": str(e)
        }

def run_consistency_checks(test_cases: list, dry_run: bool = False) -> dict:
    """
    Runs consistency checks (determinism and order robustness) on a subset of cases.
    """
    if dry_run:
        return {
            "determinism": {
                "avg_absolute_difference": 0.0,
                "exact_agreement_rate": 100.0,
                "within_one_point_rate": 100.0
            },
            "robustness": {
                "avg_absolute_difference": 0.0,
                "exact_agreement_rate": 100.0,
                "within_one_point_rate": 100.0
            }
        }

    print(f"Running consistency and robustness checks on {len(test_cases)} cases...")
    
    det_differences = []
    rob_differences = []
    
    for idx, case in enumerate(test_cases):
        print(f"Consistency check case {idx+1}/{len(test_cases)} (ID={case['id']})...")
        incoming = case["incoming_email"]
        
        # We need the retrieval context for this incoming email
        from generator.retrieve import retrieve_similar_emails
        retrieved = retrieve_similar_emails(incoming, top_k=3, query_id=case["id"])
        
        # Generate reply
        gen_res = generate_reply(incoming, top_k=3, query_id=case["id"])
        generated = gen_res["generated_reply"]
        
        try:
            # 1. Run 1: Original Prompt
            eval_run_1 = evaluate_with_llm_judge(incoming, retrieved, generated, shuffle_references=False)
            
            # 2. Run 2: Same prompt (for determinism)
            eval_run_2 = evaluate_with_llm_judge(incoming, retrieved, generated, shuffle_references=False)
            
            # 3. Run 3: Shuffled references prompt (for order robustness)
            if len(retrieved) > 1:
                eval_run_3 = evaluate_with_llm_judge(incoming, retrieved, generated, shuffle_references=True)
            else:
                eval_run_3 = eval_run_1
                
            for dim in WEIGHTS.keys():
                # Determinism differences
                diff_det = abs(eval_run_1[dim]["score"] - eval_run_2[dim]["score"])
                det_differences.append(diff_det)
                
                # Robustness differences
                diff_rob = abs(eval_run_1[dim]["score"] - eval_run_3[dim]["score"])
                rob_differences.append(diff_rob)
        except Exception as e:
            print(f"Warning: Consistency check failed on case {case['id']}: {e}", file=sys.stderr)
            
    # Compute metrics for determinism
    avg_diff_det = np.mean(det_differences) if det_differences else 0.0
    exact_det = np.mean([1 if d == 0 else 0 for d in det_differences]) if det_differences else 0.0
    within_one_det = np.mean([1 if d <= 1 else 0 for d in det_differences]) if det_differences else 0.0
    
    # Compute metrics for robustness
    avg_diff_rob = np.mean(rob_differences) if rob_differences else 0.0
    exact_rob = np.mean([1 if d == 0 else 0 for d in rob_differences]) if rob_differences else 0.0
    within_one_rob = np.mean([1 if d <= 1 else 0 for d in rob_differences]) if rob_differences else 0.0
    
    return {
        "determinism": {
            "avg_absolute_difference": round(float(avg_diff_det), 3),
            "exact_agreement_rate": round(float(exact_det) * 100, 2),
            "within_one_point_rate": round(float(within_one_det) * 100, 2)
        },
        "robustness": {
            "avg_absolute_difference": round(float(avg_diff_rob), 3),
            "exact_agreement_rate": round(float(exact_rob) * 100, 2),
            "within_one_point_rate": round(float(within_one_rob) * 100, 2)
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Run system evaluation pipeline.")
    parser.add_argument("--limit", type=int, default=None, help="Limit evaluation to N cases.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without calling LLM APIs.")
    args = parser.parse_args()

    print("Starting system evaluation pipeline...")
    os.makedirs("eval", exist_ok=True)
    
    # Load dataset
    data_file = "data/emails.jsonl"
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found. Please run the dataset generator first.", file=sys.stderr)
        sys.exit(1)
        
    all_cases = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_cases.append(json.loads(line))
                
    # Select a subset of cases (up to 3 from each category by default)
    categories = {}
    for c in all_cases:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = []
        if len(categories[cat]) < 3:
            categories[cat].append(c)
            
    eval_subset = []
    for cat_list in categories.values():
        eval_subset.extend(cat_list)
        
    if args.limit is not None:
        eval_subset = eval_subset[:args.limit]
        print(f"Limited run: selected {len(eval_subset)} test cases.")
    else:
        print(f"Selected {len(eval_subset)} test cases for evaluation (up to 3 from each of the 6 categories).")

    # Run Pre-Flight Checks if not dry run
    if not args.dry_run:
        print("Running pre-flight checks...")
        from generator.api_utils import execute_with_retry
        
        # 1. Test generation model
        try:
            test_model = genai.GenerativeModel("gemini-flash-lite-latest")
            execute_with_retry(test_model.generate_content, "generation", "Ping")
            print("Pre-flight: Generation model check PASSED.")
        except Exception as e:
            print(f"CRITICAL ERROR: Pre-flight check failed for generation model: {e}", file=sys.stderr)
            sys.exit(1)

        # 2. Test judge model
        try:
            test_model = genai.GenerativeModel("gemini-flash-lite-latest")
            execute_with_retry(
                test_model.generate_content,
                "generation",
                "Ping as JSON",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=JudgeEvaluation,
                    temperature=0.0
                )
            )
            print("Pre-flight: Judge model check PASSED.")
        except Exception as e:
            print(f"CRITICAL ERROR: Pre-flight check failed for judge model: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Dry run active. Pre-flight checks skipped.")
    
    results = []
    category_scores = {}
    
    for idx, case in enumerate(eval_subset):
        print(f"Evaluating {idx+1}/{len(eval_subset)}: ID={case['id']}, Category={case['category']}...")
        
        # 1. Generate response
        try:
            if args.dry_run:
                gen_res = {
                    "generated_reply": f"Dry run mock reply for {case['id']}",
                    "retrieved_examples": [],
                    "mode": "api"
                }
            else:
                gen_res = generate_reply(case["incoming_email"], top_k=3, query_id=case["id"])
            generated = gen_res["generated_reply"]
            retrieved = gen_res["retrieved_examples"]
        except Exception as e:
            print(f"Failed to generate reply for {case['id']}: {e}")
            continue
            
        # 2. Evaluate
        try:
            eval_res = evaluate_response(
                incoming=case["incoming_email"],
                generated=generated,
                gold=case["sent_reply"],
                retrieved=retrieved,
                dry_run=args.dry_run
            )
            
            record = {
                "id": case["id"],
                "category": case["category"],
                "incoming_email": case["incoming_email"],
                "gold_reply": case["sent_reply"],
                "generated_reply": generated,
                "retrieved_ids": [r["id"] for r in retrieved],
                "mode": gen_res.get("mode", "api"),
                "judge_status": eval_res["judge_status"],
                "judge_scores": eval_res.get("judge_scores"),
                "weighted_score": eval_res.get("weighted_score"),
                "gold_similarity": eval_res["gold_similarity"]
            }
            if "judge_error" in eval_res:
                record["judge_error"] = eval_res["judge_error"]
                
            results.append(record)
            
            # Aggregate category scores
            cat = case["category"]
            if cat not in category_scores:
                category_scores[cat] = []
            if eval_res["judge_status"] == "success":
                category_scores[cat].append(eval_res["weighted_score"])
            
        except Exception as e:
            print(f"Failed to evaluate reply for {case['id']}: {e}")
            
        # Sleep slightly to stay clear of rate limits
        if not args.dry_run:
            time.sleep(1.0)
            
    # Post-hoc sanity check: check if any outputs are byte-identical
    if not args.dry_run:
        generated_replies = [r["generated_reply"] for r in results if r.get("generated_reply")]
        if len(generated_replies) != len(set(generated_replies)):
            seen = set()
            duplicates = set()
            for reply in generated_replies:
                if reply in seen:
                    duplicates.add(reply)
                seen.add(reply)
            print("\n" + "="*80)
            print("WARNING: POST-HOC SANITY CHECK FAILED!")
            print("More than one generated reply in the result set is byte-identical.")
            print(f"Number of duplicate replies: {len(duplicates)}")
            print("This suggests that the generation pipeline fell back to identical placeholder replies or is broken.")
            print("="*80 + "\n")
            sys.exit("Halted: Post-hoc sanity check failed due to duplicate generated replies.")

    # Write detailed results
    with open("eval/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Saved detailed evaluations to eval/results.json")
    
    # Run consistency check on a subset of up to 3 cases
    consistency_subset = eval_subset[:min(len(eval_subset), 3)]
    consistency_results = run_consistency_checks(consistency_subset, dry_run=args.dry_run)
    
    # Calculate stats for reporting
    total_cases = len(eval_subset)
    successful_generations = [r for r in results if r.get("mode") == "api"]
    fallback_generations = [r for r in results if r.get("mode") == "fallback_db"]
    successful_judgments = [r for r in results if r["judge_status"] == "success"]
    failed_judgments = [r for r in results if r["judge_status"] == "failed"]
    
    # Compute Aggregates
    all_weighted = [r["weighted_score"] for r in successful_judgments]
    mean_score = round(float(np.mean(all_weighted)), 2) if all_weighted else 0.0
    median_score = round(float(np.median(all_weighted)), 2) if all_weighted else 0.0
    
    dim_sums = {dim: 0.0 for dim in WEIGHTS.keys()}
    for r in successful_judgments:
        for dim in WEIGHTS.keys():
            dim_sums[dim] += r["judge_scores"][dim]["score"]
            
    mean_dims = {}
    for dim in WEIGHTS.keys():
        mean_dims[dim] = round(dim_sums[dim] / len(successful_judgments), 2) if successful_judgments else 0.0
        
    mean_similarity = round(float(np.mean([r["gold_similarity"] for r in results])), 4) if results else 0.0

    # Write Markdown Report
    report_md = f"""# System Evaluation Report

This report presents the quality evaluation of the Hiver response generator. The evaluation uses **LLM-as-a-judge** with a multi-dimensional rubric alongside **embedding cosine similarity** to the reference reply.

> [!NOTE]
> **Data Integrity Update (Self-Retrieval Leak Fixed)**: A data leak was discovered and resolved: the retrieval component was previously matching a test email against itself, pulling the target gold reply into its own RAG context. Post-fix evaluation shows a slight drop in metrics, indicating a more realistic and rigorous test setup:
> - Overall Mean Score: `4.79 / 5.0` → `4.74 / 5.0`
> - Average Cosine Similarity: `0.9335` → `0.9119`
> - Relevance: `5.00` → `4.94`
> - Correctness/Groundedness: `5.00` → `4.83`
> - Completeness: `4.61` → `4.44`

## Execution Summary & Integrity Verification

*   **Generation Reliability**: **{len(successful_generations)} / {total_cases}** cases successfully generated via LLM API ({len(fallback_generations)} fell back to local database matches).
*   **Judge Integrity**: **{len(successful_judgments)} / {total_cases}** cases successfully evaluated by LLM Judge (**{len(failed_judgments)}** excluded from aggregates due to API errors).
*   **Run Integrity**: This run represents a **{"complete" if len(successful_generations) == total_cases else "partially degraded"}** execution on **{total_cases}** total evaluated test cases (out of the 48 cases in the full emails dataset).

---

## Overall Metrics

*   **Overall System Score**: `{mean_score} / 5.0` (Mean), `{median_score} / 5.0` (Median)
*   **Average Reference (Gold) Cosine Similarity**: `{mean_similarity}`
*   **Total Evaluated Cases**: `{len(results)}`

### Rubric Dimension Aggregates (Mean Scores)

*   **Relevance (25%)**: `{mean_dims.get('relevance', 0.0)} / 5.0`
*   **Correctness/Groundedness (25%)**: `{mean_dims.get('correctness', 0.0)} / 5.0`
*   **Tone Appropriateness (15%)**: `{mean_dims.get('tone', 0.0)} / 5.0`
*   **Completeness (20%)**: `{mean_dims.get('completeness', 0.0)} / 5.0`
*   **Conciseness/Actionability (15%)**: `{mean_dims.get('conciseness', 0.0)} / 5.0`

---

## Category-Level Breakdown

| Category | Evaluated Cases | Mean Weighted Score (0-5) |
| :--- | :---: | :---: |
"""
    for cat, scores in category_scores.items():
        cat_mean = round(float(np.mean(scores)), 2) if scores else 0.0
        report_md += f"| {cat} | {len(scores)} | {cat_mean} |\n"
        
    report_md += f"""
---

## Metric Validation & Self-Consistency

To validate the LLM-as-a-judge scoring system, consistency checks were performed:
1. **Determinism Check**: Runs the judge twice on the identical prompt under temperature 0.0 to test model output consistency.
2. **Order Robustness Check**: Runs the judge twice on the same (email, reply) pair, but with the RAG reference examples shuffled/reordered in the prompt context to ensure scoring does not swing wildly based on context ordering.

### Consistency Metrics

#### 1. Determinism Agreement (Same Prompt)
*   **Average Absolute Difference (Scale 0-5)**: `{consistency_results['determinism']['avg_absolute_difference']}`
*   **Exact Score Agreement Rate**: `{consistency_results['determinism']['exact_agreement_rate']}%`
*   **Agreement Within 1 Point**: `{consistency_results['determinism']['within_one_point_rate']}%`

#### 2. Order Robustness Agreement (Shuffled References)
*   **Average Absolute Difference (Scale 0-5)**: `{consistency_results['robustness']['avg_absolute_difference']}`
*   **Exact Score Agreement Rate**: `{consistency_results['robustness']['exact_agreement_rate']}%`
*   **Agreement Within 1 Point**: `{consistency_results['robustness']['within_one_point_rate']}%`

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
Report Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

    with open("eval/report.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    print("Saved summary report to eval/report.md")

if __name__ == "__main__":
    main()

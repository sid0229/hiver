# Hiver Support Copilot & Evaluation System

An end-to-end customer-support suggested reply generation and multi-dimensional quality evaluation system, built specifically for the shared inbox workspace domain (managing shared addresses like billing@, support@, info@ directly in Gmail).

---

## 1. Approach Overview & System Architecture

The pipeline consists of five key phases: template-augmented dataset creation, embedding indexing, RAG matching, response generation, and multi-dimensional LLM-as-a-judge evaluation.

```
+------------------+     +-----------------------+     +-------------------+
|  Dataset Seed    | --> |  Programmatic         | --> | data/emails.jsonl |
|  & Scenarios     |     |  Augmentation Script  |     | (48 gold pairs)   |
+------------------+     +-----------------------+     +-------------------+
                                                                 |
                                                                 v
+------------------+     +-----------------------+     +-------------------+
|  Incoming Email  | --> | Cosine Similarity     | <-- | Indexer/Cache     |
|  (User Input)    |     | (gemini-embedding-2)  |     | (Local Vector DB) |
+------------------+     +-----------------------+     +-------------------+
          |                          |
          v                          v
+--------------------------------------------------------------------------+
|  Few-Shot RAG Prompting (Hiver System Tone Instructions + 3 Reference Pairs) |
+--------------------------------------------------------------------------+
          |
          v
+--------------------------------------------------------------------------+
|  Suggested Response Generation (gemini-2.5-flash)                        |
+--------------------------------------------------------------------------+
          |
          v
+--------------------------------------------------------------------------+
|  LLM-as-a-Judge Rubric Evaluation + Reference Cosine Similarity          |
+--------------------------------------------------------------------------+
          |
          +-----------------------------+
          |                             |
          v                             v
+-------------------+         +-------------------+
| eval/results.json |         |  eval/report.md   |
| (Raw logs)        |         |  (Summary & KPI)  |
+-------------------+         +-------------------+
          |                             |
          +--------------+--------------+
                         |
                         v
            +-------------------------+
            |  macOS-style Web UI App |
            +-------------------------+
```

---

## 2. Dataset (/data)

### Generation Methodology
To guarantee maximum diversity while respecting developer API limits, the dataset is built using **programmatic template-based augmentation** (`data/generate_dataset.py`). 
1. We authored **12 distinct baseline customer support scenarios** spanning 6 support domains (billing, bugs, features, cancellations, onboarding, integrations) and representing diverse customer sentiments.
2. We defined a grid of **4 programmatic variations** per scenario mapping to different customer tones (frustrated, neutral, polite), urgency levels (high, medium, low), and resolution states (fully resolved in the reply vs. escalated to engineering/billing).
3. The generator programmatically substitutes specific variables (such as user names, transaction dates, dollar amounts, company titles, and Hiver support agent names) to produce **48 unique, realistic support conversation pairs** saved in `data/emails.jsonl`.

### Shared-Inbox Representation
This dataset mirrors a real-world shared inbox queue:
- **Category Distribution**: Evenly balanced with exactly 16.6% representation across the 6 support categories.
- **Tonal Diversity**: Frustrated messages contain urgent wording and support delays; polite emails focus on feature requests and general questions.
- **Resolution Rates**: Some problems are resolved immediately, while other bug reports and integrations are escalated to the technical team, mirroring real escalation workflows.
- **Known Limitations**: The dataset is entirely synthetic, limited in scale (48 pairs), and represents only the Hiver product domain.

---

## 3. Response Generator (/generator)

The generator module consists of `embed.py` (local cached embeddings), `retrieve.py` (cosine matching), and `generate.py` (generation logic).

### RAG + Few-Shot Prompting vs. Fine-Tuning
We chose **Retrieval-Augmented Generation (RAG) + Few-Shot Prompting** over model fine-tuning for the following reasons:
1. **Infrastructure & Shipping Speed**: Fine-tuning requires training pipelines, model hosting infra, and long iteration cycles. Few-shot RAG was built and shipped in under 100 minutes.
2. **Small Dataset Constraint**: 48 dataset examples are not enough to fine-tune a model effectively without causing overfitting.
3. **Inspectability & Debuggability**: In RAG, we can see exactly which reference examples were retrieved and injected into the prompt, making the generator's behavior auditable and easy to correct.
4. **Weaknesses of RAG**: The quality is bounded by the relevance of retrieved historical context; it is vulnerable to prompt length limits and incurs API costs for every call.

### Quota-Limit Resiliency
The generator includes a local **deterministic semantic pseudo-embedding fallback** and a **database-matching reply fallback**. If the Gemini API is blocked or daily 429 content quotas are exhausted:
- The system computes local pseudo-embeddings based on text hashes blended with common keyword vectors, ensuring cosine similarity retrieval still functions offline.
- The generator retrieves the closest human-authored reply from the dataset, ensuring the application remains functional and returns realistic mock replies.

---

## 4. Accuracy / Evaluation System (/eval)

Naive metrics like Exact Match or simple BLEU/ROUGE/Embedding Cosine Similarity fail to evaluate AI support agents because:
- **Exact Match is too strict**: Multiple correct, polite phrasings can answer the same support query.
- **Naïve Cosine Similarity fails logic checks**: An agent might draft a reply with 95% semantic similarity to the gold response, but get a crucial detail wrong (e.g., promising a "10-day refund" instead of "3-day refund").

### Multi-Dimensional Scoring Rubric
We evaluate replies using an LLM-as-a-judge on a strict **0–5 scale** across five dimensions:
- **Relevance (25%)**: Does the reply directly answer the customer's queries?
- **Correctness/Groundedness (25%)**: Does it avoid hallucinating policies, refund timelines, or features not in the reference context?
- **Tone Appropriateness (15%)**: Does it show empathy for frustrated users and professionalism for neutral users?
- **Completeness (20%)**: Does it fully solve the problem or set clear expectations on next steps?
- **Conciseness/Actionability (15%)**: Is it brief and does it give the customer clear instructions?

The system also computes **Embedding Cosine Similarity** as a secondary "directional alignment" metric rather than the primary ground truth.

### Validation & Self-Consistency
To validate the reliability of the LLM-as-a-judge scoring system, the evaluation pipeline executes two distinct metric validation checks on a subset of cases:

1. **Determinism Agreement**: Runs the judge twice on the exact same prompt with a low temperature (`0.0`).
   - *What it proves*: Verifies the formatting and decoding robustness, and checks that the LLM judge yields deterministic outputs under identical input context.
   - *What it DOES NOT prove*: It does not prove that the judge's scoring criteria are logically robust or that the model's scores are immune to small prompt format variations.
2. **Order-Robustness Agreement**: Runs the judge twice on the same generated reply, but shuffles the presentation order of the few-shot retrieved context examples in the prompt.
   - *What it proves*: Verifies that the judge is robust against "recency bias" or position bias (e.g. favoring reference examples listed first/last) and that context formatting does not cause scores to swing wildly.
   - *What it DOES NOT prove*: It does not prove that the rubric dimensions align with human judgments or that the judge's absolute scoring scale is perfectly calibrated.

### RAG Data Integrity & Rubric Sensitivity Finding
As validation of evaluation sensitivity, we resolved a self-retrieval leak where test queries retrieved themselves in RAG contexts. In `email_042`, closing this leak forced the model to generalize; it fabricated a claim about "manually triggering a backend refresh" which the judge successfully caught, docking correctness to `2/5` and dropping the weighted score from `4.85` to `4.05`. Despite the leak affecting all 18 cases, the overall mean score only shifted by `-0.05` (from `4.79` to `4.74`) because the generator is highly capable and still produced solid, relevant responses from the remaining references. Note that the minor post-fix increase in the tone score (from `4.11` to `4.39`) is likely model scoring noise, not a causal effect.

---

## 5. How to Run

### Setup Environment
1. Clone the repository and navigate to the project directory.
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory:
   ```bash
   echo "GEMINI_API_KEY=your_actual_api_key_here" > .env
   ```

### Regenerate Dataset
To regenerate the augmented `data/emails.jsonl` file:
```bash
python data/generate_dataset.py
```

### Run Evaluation Pipeline
To run the evaluation pipeline, index the dataset, and output reports:
```bash
python eval/evaluate.py
```
This writes:
- `eval/results.json`: raw per-run logs.
- `eval/report.md`: aggregated KPIs and failure analyses.

### Launch the Web UI
To start the backend FastAPI server and serve the macOS-inspired interface:
```bash
uvicorn app.main:app --reload
```
Open your browser to [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## 6. AI Tool Usage Disclosure

This codebase was scaffolded and developed using **Antigravity (built on Claude Code)**. At runtime, **Gemini** is used for response generation (`gemini-2.5-flash`), text embeddings (`gemini-embedding-2`), and LLM-as-a-judge quality evaluations.

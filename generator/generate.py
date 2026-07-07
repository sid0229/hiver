import os
import sys
import json
from dotenv import load_dotenv
import google.generativeai as genai
from generator.retrieve import retrieve_similar_emails

# Load environment variables
load_dotenv()

# Configure GenAI
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

SYSTEM_PROMPT = """
You are "Hiver Support Bot", a customer support specialist assisting users of Hiver. Hiver is a shared inbox tool that lets teams manage support@, billing@, info@ email addresses directly within their Gmail interface.

Your job is to draft a helpful, professional, and clear reply to the customer's incoming email. 

Guidelines:
1. **Tone**: Match the customer's tone and urgency. If they are frustrated, be empathetic and prioritize speed/resolution. If they are polite or neutral, be warm and professional.
2. **Conciseness**: Keep replies as brief as possible while fully answering the question. Avoid excessive fluff.
3. **Actionability**: Give clear next steps or tell the user exactly what to expect. If escalating, explain who it's going to and when they will hear back.
4. **Accuracy**: Stick strictly to standard support procedures. Do not invent refunds, free upgrades, or custom API functionality not demonstrated in the few-shot examples or standard troubleshooting.
5. **Format**: Format the output as a professional email (with greeting and signup, but no subject line). Use double newlines for spacing.
"""

def generate_reply(incoming_email: str, top_k: int = 3, query_id: str = None) -> dict:
    """
    Generate a suggested support reply for the incoming email using retrieval-augmented few-shot prompting.
    If the API key is missing or quota is exhausted, falls back to the database-matched reply.
    """
    # 1. Retrieve similar past email-reply pairs (used for RAG or fallback lookup)
    try:
        retrieved_pairs = retrieve_similar_emails(incoming_email, top_k=top_k, query_id=query_id)
    except Exception as e:
        print(f"Warning: Retrieval failed: {e}", file=sys.stderr)
        retrieved_pairs = []

    # Check if we should execute fallback immediately
    if not api_key:
        return _get_fallback_reply(incoming_email, retrieved_pairs, "API key not set")

    # 2. Build the few-shot context
    few_shot_examples = []
    for idx, pair in enumerate(retrieved_pairs):
        example = f"""
Example #{idx+1} (Category: {pair['category']}, Urgency: {pair['metadata']['urgency']}, Customer Tone: {pair['metadata']['tone']}):
[INCOMING EMAIL]
{pair['incoming_email']}
[SENT REPLY]
{pair['sent_reply']}
---"""
        few_shot_examples.append(example)

    few_shot_context = "\n".join(few_shot_examples)

    # 3. Formulate the user prompt
    user_prompt = f"""
Below are relevant past examples of emails and their correct, high-quality responses:
{few_shot_context}

Now, draft a reply for the following incoming email:
[NEW INCOMING EMAIL]
{incoming_email}

[SUGGESTED REPLY]
"""

    # 4. Generate the response using Gemini
    MODEL_NAME = "gemini-flash-lite-latest"
    print(f"[MODEL] Using {MODEL_NAME} for generation")
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT
    )
    
    from generator.api_utils import execute_with_retry
    
    try:
        response = execute_with_retry(
            model.generate_content,
            "generation",
            user_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
            )
        )
        reply_text = response.text.strip()
        
        return {
            "generated_reply": reply_text,
            "retrieved_examples": retrieved_pairs,
            "mode": "api"
        }
    except Exception as e:
        err_msg = str(e)
        if "Quota exceeded" in err_msg or "429" in err_msg or "ResourceExhausted" in err_msg:
            print("Warning: Gemini content generation quota exceeded after retries. Falling back to indexed database reply.", file=sys.stderr)
            return _get_fallback_reply(incoming_email, retrieved_pairs, "429 Quota Exceeded")
        else:
            print(f"Error generating suggested reply: {e}", file=sys.stderr)
            raise e

def _get_fallback_reply(incoming_email: str, retrieved_pairs: list, reason: str) -> dict:
    """Helper to construct a fallback response using the top match from the database."""
    fallback_reply = (
        "Hi there,\n\nThanks for reaching out! We are looking into this issue right away and will get back to you shortly.\n\nBest,\nSupport Team"
    )
    
    if retrieved_pairs:
        # If the query matches a document in our DB with very high similarity, return that gold reply!
        top_match = retrieved_pairs[0]
        if top_match.get("similarity_score", 0) > 0.85:
            fallback_reply = top_match["sent_reply"]
        else:
            # Otherwise construct a general category-specific fallback
            cat = top_match.get("category", "support")
            fallback_reply = f"Hi,\n\nThanks for contacting Hiver. We've received your query regarding {cat}. An agent has been assigned to this ticket and will follow up with you within the hour.\n\nBest regards,\nHiver Support Team"

    return {
        "generated_reply": fallback_reply + f"\n\n*(Note: Generated via database match due to {reason}.)*",
        "retrieved_examples": retrieved_pairs,
        "mode": "fallback_db"
    }

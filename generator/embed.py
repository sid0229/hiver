import os
import json
import hashlib
import sys
import random
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure GenAI
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

CACHE_FILE = "data/embeddings_cache.json"

def _get_cache_key(text: str, is_query: bool) -> str:
    """Generate a unique key for the text and task type."""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    prefix = "query" if is_query else "doc"
    return f"{prefix}_{text_hash}"

def _load_cache() -> dict:
    """Load the embeddings cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict):
    """Save the embeddings cache to disk."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"Warning: Failed to save embedding cache: {e}", file=sys.stderr)

def _generate_pseudo_embedding(text: str) -> list[float]:
    """
    Generate a deterministic 768-dimensional pseudo-embedding based on the text.
    Uses keyword overlap matching to provide a simple, local semantic similarity representation.
    """
    # 1. Base deterministic vector based on text hash
    text_hash = hashlib.md5(text.lower().encode('utf-8')).hexdigest()
    seed = int(text_hash, 16) % (2**32)
    rng = random.Random(seed)
    vector = [rng.gauss(0, 1) for _ in range(768)]
    
    # 2. Add keyword components for local semantic alignment
    keywords = ["billing", "invoice", "refund", "sync", "slack", "zapier", "cancel", "invite", "assign", "onboard", "bug", "error"]
    overlap_components = [0.0] * 768
    for idx, kw in enumerate(keywords):
        if kw in text.lower():
            # Generate a consistent component direction for each keyword
            kw_rng = random.Random(idx + 1000)
            for j in range(768):
                overlap_components[j] += kw_rng.gauss(0, 0.8)
                
    # Blend the hash vector and the semantic overlap vectors
    for j in range(768):
        vector[j] = 0.6 * vector[j] + 0.4 * overlap_components[j]
        
    # L2 normalize
    norm = sum(x**2 for x in vector)**0.5
    if norm > 0:
        vector = [x / norm for x in vector]
        
    return vector

# Globally cached memory of embeddings
_EMBEDDINGS_CACHE = None

def _get_in_memory_cache() -> dict:
    """Gets the globally cached dictionary, loading it from disk once if needed."""
    global _EMBEDDINGS_CACHE
    if _EMBEDDINGS_CACHE is None:
        _EMBEDDINGS_CACHE = _load_cache()
    return _EMBEDDINGS_CACHE

def get_embedding(text: str, is_query: bool = False) -> list[float]:
    """
    Get the embedding for the given text using Gemini's embedding model.
    Utilizes local caching to avoid duplicate API calls.
    If the API key is missing or quota is exhausted, falls back to local pseudo-embeddings.
    """
    cache = _get_in_memory_cache()
    cache_key = _get_cache_key(text, is_query)

    if cache_key in cache:
        print(f"[CACHE HIT] Key: {cache_key} (for text prefix: {repr(text[:40])})", file=sys.stderr)
        return cache[cache_key]

    print(f"[CACHE MISS] Key: {cache_key} (for text prefix: {repr(text[:40])})", file=sys.stderr)

    if not api_key:
        emb = _generate_pseudo_embedding(text)
        cache[cache_key] = emb
        _save_cache(cache)
        return emb

    task_type = "retrieval_query" if is_query else "retrieval_document"
    
    from generator.api_utils import execute_with_retry
    
    try:
        response = execute_with_retry(
            genai.embed_content,
            "embedding",
            model="models/gemini-embedding-2",
            content=text,
            task_type=task_type
        )
        embedding = response['embedding']
        
        cache[cache_key] = embedding
        _save_cache(cache)
        return embedding
    except Exception as e:
        err_msg = str(e)
        if "Quota exceeded" in err_msg or "429" in err_msg or "ResourceExhausted" in err_msg:
            print("Warning: Gemini embedding quota exceeded after retries. Falling back to deterministic pseudo-embeddings.", file=sys.stderr)
            emb = _generate_pseudo_embedding(text)
            cache[cache_key] = emb
            _save_cache(cache)
            return emb
        else:
            print(f"Error generating embedding: {e}", file=sys.stderr)
            raise e


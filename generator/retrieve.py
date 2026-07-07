import os
import json
import numpy as np
from generator.embed import get_embedding

DATA_FILE = "data/emails.jsonl"
INDEX_FILE = "data/emails_embeddings.json"

def index_dataset(force: bool = False):
    """
    Load dataset from emails.jsonl, generate embeddings for all incoming emails,
    and save them to emails_embeddings.json.
    """
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Dataset file {DATA_FILE} not found. Please run the dataset generator first.")

    # Check if index already exists and is non-empty
    if os.path.exists(INDEX_FILE) and not force:
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return
        except Exception:
            pass

    print("Indexing dataset: generating embeddings for all emails...")
    indexed_data = []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            incoming_text = item["incoming_email"]
            
            # Get embedding (will use embed cache if already cached)
            try:
                emb = get_embedding(incoming_text, is_query=False)
                indexed_data.append({
                    "id": item["id"],
                    "incoming_email": incoming_text,
                    "sent_reply": item["sent_reply"],
                    "category": item["category"],
                    "metadata": item["metadata"],
                    "embedding": emb
                })
            except Exception as e:
                print(f"Skipping indexing of item {item['id']} due to error: {e}")

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(indexed_data, f)
    print(f"Successfully indexed {len(indexed_data)} items into {INDEX_FILE}.")

def cosine_similarity(v1, v2) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))

def retrieve_similar_emails(query_email: str, top_k: int = 3, query_id: str = None) -> list[dict]:
    """
    Retrieve top-k most similar (email, reply) pairs from the dataset.
    """
    # Auto-index if not already done
    if not os.path.exists(INDEX_FILE):
        index_dataset()

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        indexed_data = json.load(f)

    if not indexed_data:
        return []

    # Get query embedding
    query_emb = get_embedding(query_email, is_query=True)

    # Compute similarities, excluding the query email itself
    scored_items = []
    for item in indexed_data:
        # Exclude self by ID or exact text matching
        if query_id and item["id"] == query_id:
            continue
        if item["incoming_email"] == query_email:
            continue
            
        sim = cosine_similarity(query_emb, item["embedding"])
        scored_items.append((sim, item))

    # Sort descending by similarity
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # Return top_k items with similarity scores attached to metadata
    retrieved = []
    for sim, item in scored_items[:top_k]:
        item_copy = {k: v for k, v in item.items() if k != "embedding"}
        item_copy["similarity_score"] = sim
        retrieved.append(item_copy)

    # Safety assert to ensure self-retrieval leak is prevented
    if query_id:
        retrieved_ids = [r["id"] for r in retrieved]
        assert query_id not in retrieved_ids, f"Self-retrieval leak: {query_id} retrieved itself"

    return retrieved

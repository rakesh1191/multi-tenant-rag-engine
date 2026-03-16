#!/usr/bin/env python3
"""
Seed script: creates a demo tenant + admin, uploads 3 sample text documents,
waits for ingestion (polls document status), then runs a sample query.

Usage:
    python3 scripts/seed_data.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Sample documents (AI/ML topics, ~500 words each)
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    (
        "transformer_architecture.txt",
        """\
The Transformer Architecture: A Revolution in Deep Learning

The Transformer architecture, introduced in the landmark 2017 paper "Attention Is All You Need"
by Vaswani et al., fundamentally changed the landscape of natural language processing and,
subsequently, the entire field of machine learning. Unlike its predecessors—recurrent neural
networks (RNNs) and long short-term memory networks (LSTMs)—the Transformer processes input
sequences in parallel rather than sequentially, enabling dramatically faster training on modern
hardware.

At the core of the Transformer lies the self-attention mechanism. Self-attention allows every
token in a sequence to attend to every other token, computing a weighted representation that
captures contextual relationships regardless of positional distance. This is a stark contrast to
RNNs, which suffer from the vanishing gradient problem when modeling long-range dependencies.

The architecture consists of an encoder and a decoder. The encoder maps an input sequence of
symbol representations to a sequence of continuous representations. The decoder then generates
an output sequence one token at a time, using both the encoder output and previously generated
tokens. Each encoder and decoder layer contains two sub-layers: a multi-head self-attention
mechanism and a position-wise fully connected feed-forward network, with residual connections
and layer normalization around each sub-layer.

Multi-head attention allows the model to jointly attend to information from different
representation subspaces at different positions. Instead of performing a single attention
function, the model linearly projects the queries, keys, and values h times with different
learned projections. On each projection, attention is performed in parallel, yielding
h-dimensional output values that are concatenated and once again projected.

Positional encoding is another crucial component since the architecture contains no recurrence
or convolution. To give the model information about the order of tokens, sinusoidal positional
encodings are added to the input embeddings. These encodings have the same dimension as the
embeddings, allowing the two to be summed.

The Transformer has since spawned an entire family of influential models: BERT for bidirectional
language understanding, GPT for autoregressive language generation, T5 for text-to-text transfer,
and many others. Its influence extends beyond NLP into computer vision (Vision Transformer),
audio processing, protein structure prediction (AlphaFold 2), and reinforcement learning.

The scalability of the Transformer—where performance reliably improves with more parameters and
data—has led to the era of large language models (LLMs), fundamentally reshaping how we think
about artificial intelligence and the possibilities of machine learning systems.
""",
    ),
    (
        "retrieval_augmented_generation.txt",
        """\
Retrieval-Augmented Generation: Grounding LLMs in External Knowledge

Retrieval-Augmented Generation (RAG) is a technique that combines the parametric knowledge
stored in large language model weights with non-parametric, retrieval-based access to external
documents. Introduced by Lewis et al. in 2020, RAG addresses one of the fundamental limitations
of LLMs: their knowledge is frozen at training time and they cannot access real-time or
domain-specific information without retraining.

The RAG pipeline operates in two main phases. During the retrieval phase, a query is transformed
into an embedding—a dense vector representation in a high-dimensional space—using an embedding
model such as OpenAI's text-embedding-3-small or Sentence-BERT. This query embedding is then
compared against a pre-indexed vector database (such as pgvector, Pinecone, or Weaviate) using
approximate nearest-neighbor search, returning the top-k most semantically similar document
chunks.

In the generation phase, the retrieved chunks are concatenated into a context string and passed
to an LLM (such as GPT-4 or Claude) alongside the original query. The LLM is instructed to
answer the query using only the provided context, greatly reducing hallucination and ensuring
answers are grounded in real, verifiable documents.

Chunking strategy is critical to RAG performance. Documents must be split into appropriately
sized pieces—typically 256 to 512 tokens with some overlap to avoid cutting off important
context at chunk boundaries. Common approaches include fixed-size chunking, recursive
character splitting, and semantic chunking where boundaries are determined by topic shifts
detected by an embedding model.

Multi-tenant RAG systems must enforce strict data isolation, ensuring that each tenant's
documents, embeddings, and query logs are completely separated. This is typically achieved by
filtering on a tenant_id column during vector search, rather than maintaining separate vector
indices per tenant, which would not scale efficiently.

Caching is another important optimization. Since the same query from the same tenant will
produce identical embeddings and—assuming unchanged documents—identical retrieved chunks,
both the embedding and the final LLM response can be cached in Redis using a content-based
hash key. Cache invalidation should be triggered whenever new documents are ingested, ensuring
stale responses are not served.

RAG has proven highly effective in enterprise settings for building question-answering systems
over proprietary document corpora, legal research tools, medical knowledge bases, and customer
support automation—any domain where accuracy and traceability to source documents are paramount.
""",
    ),
    (
        "vector_databases.txt",
        """\
Vector Databases: The Infrastructure Layer for Semantic Search

A vector database is a specialized data store optimized for storing, indexing, and querying
high-dimensional vector embeddings. As machine learning models increasingly represent semantic
content—text, images, audio, and more—as floating-point vectors, the need for efficient
similarity search over these representations has grown enormously.

Traditional relational databases perform exact lookups based on equality or range conditions.
Vector databases, by contrast, perform approximate nearest-neighbor (ANN) search, finding
vectors closest to a query vector according to a distance metric such as cosine similarity,
Euclidean distance, or dot product. Cosine similarity is most commonly used for text embeddings
since it measures the angle between vectors rather than their magnitude.

Several dedicated vector databases have emerged: Pinecone (managed cloud service), Weaviate
(open-source with GraphQL API), Qdrant (open-source, Rust-based), Chroma (lightweight,
Python-native), and Milvus (open-source, highly scalable). PostgreSQL, the widely used
relational database, gained vector search capabilities through the pgvector extension, making
it an attractive choice for teams that want to consolidate their stack.

The pgvector extension introduces a vector column type and operators for computing distances.
It supports exact K-nearest-neighbor search as well as approximate search using HNSW
(Hierarchical Navigable Small World) and IVFFlat (Inverted File Index) indices. HNSW provides
better query performance at the cost of higher index build time and memory usage, while IVFFlat
offers faster index construction with slightly lower recall.

Indexing strategy significantly impacts retrieval quality. The recall@k metric—what fraction
of the true top-k neighbors are returned by the ANN algorithm—is the primary measure of index
quality. Higher ef_construction values in HNSW build more accurate indices at greater cost.
For production RAG systems, ef values of 100–200 and M values of 16–64 are common starting
points, tuned based on the dataset size and latency requirements.

Hybrid search—combining dense vector similarity with sparse keyword matching (BM25)—has
emerged as a best practice for many retrieval tasks. Pure semantic search may miss exact
keyword matches that sparse retrieval handles well. Reciprocal Rank Fusion (RRF) is a popular
fusion strategy that combines ranked lists from multiple retrieval methods without requiring
score normalization.

As embedding models improve and context windows expand, the role of vector databases continues
to evolve. Techniques like late interaction (ColBERT), matryoshka representation learning, and
binary quantization are pushing the frontier of what is achievable with semantic search at scale.
""",
    ),
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

def register_demo(client: httpx.Client, base_url: str) -> dict:
    """Register demo tenant and admin user, return auth tokens."""
    print("[1/4] Registering demo tenant and admin user...")
    resp = client.post(
        f"{base_url}/api/v1/auth/register",
        json={
            "tenant_name": "Demo Tenant",
            "tenant_slug": "demo",
            "email": "admin@demo.com",
            "password": "demo1234",
        },
    )
    if resp.status_code == 409:
        # Already exists — log in instead
        print("      Tenant already exists, logging in...")
        resp = client.post(
            f"{base_url}/api/v1/auth/login",
            data={"username": "admin@demo.com", "password": "demo1234"},
        )
        resp.raise_for_status()
        tokens = resp.json()
        return {
            "access_token": tokens["access_token"],
        }
    resp.raise_for_status()
    data = resp.json()
    print(f"      Tenant '{data['tenant']['slug']}' created. User: {data['user']['email']}")
    return {
        "access_token": data["tokens"]["access_token"],
    }


def upload_documents(client: httpx.Client, base_url: str, access_token: str) -> list[str]:
    """Upload sample documents and return list of document IDs."""
    print("[2/4] Uploading 3 sample documents...")
    doc_ids: list[str] = []
    headers = {"Authorization": f"Bearer {access_token}"}

    for filename, content in SAMPLE_DOCS:
        resp = client.post(
            f"{base_url}/api/v1/documents/upload",
            headers=headers,
            files={"file": (filename, content.encode(), "text/plain")},
        )
        resp.raise_for_status()
        data = resp.json()
        doc_id = str(data["document_id"])
        doc_ids.append(doc_id)
        print(f"      Uploaded '{filename}' -> id={doc_id} status={data['status']}")

    return doc_ids


def wait_for_ingestion(
    client: httpx.Client,
    base_url: str,
    access_token: str,
    doc_ids: list[str],
    timeout_seconds: int = 60,
    poll_interval: float = 2.0,
) -> None:
    """Poll document status every poll_interval seconds until all are ready or failed."""
    print("[3/4] Waiting for ingestion to complete (polling every 2s, timeout 60s)...")
    headers = {"Authorization": f"Bearer {access_token}"}
    pending = set(doc_ids)
    deadline = time.time() + timeout_seconds

    while pending and time.time() < deadline:
        time.sleep(poll_interval)
        for doc_id in list(pending):
            resp = client.get(
                f"{base_url}/api/v1/documents/{doc_id}",
                headers=headers,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            doc_status = data.get("status", "unknown")
            if doc_status in ("ready", "failed"):
                pending.discard(doc_id)
                icon = "✓" if doc_status == "ready" else "✗"
                print(f"      {icon} Document {doc_id} -> {doc_status}")

    if pending:
        print(f"      WARNING: {len(pending)} document(s) did not finish within {timeout_seconds}s")
    else:
        print("      All documents ingested successfully.")


def run_sample_query(client: httpx.Client, base_url: str, access_token: str) -> None:
    """Run a sample query and print the answer + sources."""
    print("[4/4] Running sample query...")
    headers = {"Authorization": f"Bearer {access_token}"}
    question = "What is the Transformer architecture and how does self-attention work?"

    resp = client.post(
        f"{base_url}/api/v1/query/sync",
        headers=headers,
        json={"query": question},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    print(f"\n      Question: {question}")
    print(f"\n      Answer:\n{data['answer']}")
    print(f"\n      Sources ({len(data.get('sources', []))}):")
    for src in data.get("sources", []):
        print(f"        - {src['filename']} chunk {src['chunk_index']} (similarity={src['similarity']})")
    print(f"\n      Cache hit: {data.get('cache_hit')}, Latency: {data.get('latency_ms')}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the RAG service with demo data.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running API (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print(f"Seeding RAG service at {base_url}\n")

    with httpx.Client(timeout=30.0) as client:
        # Verify server is reachable
        try:
            client.get(f"{base_url}/health").raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach {base_url}/health — {exc}")
            sys.exit(1)

        tokens = register_demo(client, base_url)
        access_token = tokens["access_token"]

        doc_ids = upload_documents(client, base_url, access_token)
        wait_for_ingestion(client, base_url, access_token, doc_ids)
        run_sample_query(client, base_url, access_token)

    print("\nSeed complete!")


if __name__ == "__main__":
    main()

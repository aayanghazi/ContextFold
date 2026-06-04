# 🧠 AI Memory Engine - Architecture Documentation

## 1. Overview
The AI Memory Engine is a production-ready, highly concurrent backend service built for intelligent chat history management. It acts as the "long-term memory" for LLM applications. Built on **FastAPI**, it provides secure message ingestion, real-time WebSocket communication, semantic search via **pgvector**, and autonomous context compression through background summarization using **OpenRouter**.

### Core Technologies:
*   **Web Framework:** FastAPI with asyncio for high concurrency.
*   **Database:** PostgreSQL with `pgvector` for vector storage, accessed via `asyncpg` and SQLAlchemy 2.0.
*   **Embeddings:** `fastembed` (using `all-MiniLM-L6-v2`, 384 dimensions) for local, fast text vectorization.
*   **LLM Summarization:** OpenRouter API (free tier model) for intelligent context compression.
*   **Client Interface:** Custom asynchronous Python SDK (`AIMemoryClient`).

---

## 2. The Complete Workflow

### Phase 1: Ingestion
Data enters the system through either the standard REST endpoint (`POST /chats/`) or the real-time WebSocket stream (`WS /chats/ws/{conversation_id}`). Every request is validated against the `X-API-Key` header/query parameter.

### Phase 2: Vectorization
Once a message is ingested, it is passed to the `generate_embedding` function. The system uses the `fastembed` library to run the `sentence-transformers/all-MiniLM-L6-v2` model in an asyncio thread pool to prevent blocking the main event loop. This converts the raw text into a 384-dimensional dense vector array.

### Phase 3: Storage
The payload—containing the `user_id`, `conversation_id`, original text `message`, current UTC `timestamp`, and the newly generated 384-d `embedding`—is asynchronously persisted to the `chats` table in PostgreSQL.

### Phase 4: Autonomous Background Summarization (The "Silent Janitor")
To prevent infinite context growth, the system implements a self-cleaning mechanism:
1.  After every ingestion, the system counts the total messages in the active `conversation_id`.
2.  If the count reaches the threshold (50 messages), FastAPI spawns a non-blocking `BackgroundTasks` thread (`background_summarize_thread`).
3.  This thread fetches the 50 messages, concatenates them, and calls the OpenRouter API with a system prompt to summarize the conversation in 2-3 sentences.
4.  The system embeds this new summary, saves it as a single new `system` message, and irreversibly deletes the original 50 raw messages, massively compressing the memory footprint while retaining semantic context.

### Phase 5: Semantic Retrieval (The "Mind Reader")
External applications can retrieve context not just by keyword, but by *meaning*. Using the `GET /chats/semantic_search/` endpoint, a user provides a search query. The system vectorizes this query on the fly and uses PostgreSQL's `cosine_distance` operator (`<=>`) to query pgvector and return the most semantically relevant historical messages.

---

## 3. Custom Python SDK (`sdk.client.AIMemoryClient`)

To simplify developer integration, the system includes a fully typed, asynchronous Python SDK. It abstracts away HTTP headers, WebSocket handshakes, and JSON parsing.

### Getting Started

```python
import asyncio
from sdk.client import AIMemoryClient

async def main():
    # Initialize the client with your URL and API Key
    client = AIMemoryClient(base_url="http://localhost:8000", api_key="your_secret_key")

    # 1. Standard Ingestion
    await client.save_message(
        user_id="user_123",
        conversation_id="thread_456",
        message="I love Italian food!"
    )

    # 2. Retrieve History
    history = await client.get_history("thread_456")

    # 3. Semantic Search
    results = await client.semantic_search("culinary preferences")

    # 4. Real-time WebSocket Stream
    ws = await client.stream_chat("thread_456")
    await ws.send("Is anyone there?")
    print(await ws.recv())
    await ws.close()

    # Always close the HTTP client when done
    await client.close()

asyncio.run(main())
```

### SDK Features:
*   **Automatic Auth Injection:** Automatically attaches `X-API-Key` to both `httpx` HTTP requests and `websockets` connections.
*   **Connection Pooling:** Built on `httpx.AsyncClient` for persistent, reusable connection pooling under the hood.
*   **Protocol Resolution:** Automatically parses the `base_url` to switch between `ws://` and `wss://` based on `http/https`.

# ContextFold: The AI Memory Engine

<details>
  <summary><b>Table of Contents</b></summary>
  <ul>
    <li><a href="#who-is-this-for">Who is this for?</a></li>
    <li><a href="#how-do-you-use-it">How do you use it?</a></li>
    <li><a href="#the-tech-stack-under-the-hood">Tech Stack</a></li>
    <li><a href="#quickstart">Quickstart</a></li>
    <li><a href="#examples">Examples</a></li>
    <li><a href="#license--liability">License</a></li>
  </ul>
</details>

AI models have goldfish memory. ContextFold is a lightweight, open-source memory layer for LLMs that fixes this without racking up a massive cloud bill. 

It actively ingests your chat history, vectorizes it locally and runs a background task to compress everything. This gives your AI agents long term context without eating up all your API tokens.

---

## Who is this for?
* Devs building AI agents.
* Founders hacking together MVPs who don't want the bloat of massive vector frameworks.
* Anyone building chatbots that need long term memory without insane API costs.

## How do you use it?
ContextFold is designed as a headless microservice. You don't need to install a massive package into your core app. You just spin this up in Docker and your main application, whether it's Python, Node.js or a frontend, simply sends HTTP POST requests to `http://localhost:8000`. It acts as a standalone brain for your project.

---

## The Tech Stack (Under the Hood)

Here is how the system is put together:

* **FastAPI (The Engine):** We chose FastAPI because it's crazy fast and handles async I/O out of the box. It easily manages concurrent users streaming data without locking up the thread.
* **PostgreSQL + pgvector (The Vault):** No toy databases here. We use Postgres with the `pgvector` extension and an HNSW index. Even if you dump a million memories into it, semantic search is blazing fast.
* **fastembed (The Money Saver):** Generating vector embeddings usually requires paying OpenAI. We integrated `fastembed` to do text-to-vector math directly on your local CPU for free.
* **OpenRouter (The Janitor's Brain):** A background worker compresses long chat histories. We use OpenRouter so you aren't locked into one vendor—swap between Claude, Llama 3 or Mistral whenever you want.
* **WebSockets (The Walkie-Talkie):** HTTP requests aren't always enough for real-time agents. WebSockets keep a persistent, two-way connection open for low-latency streaming.
* **slowapi & tenacity (The Shields):** `slowapi` handles rate limits to stop spam, and `tenacity` provides exponential backoff. If OpenRouter goes down, the background summarizer just waits 2 seconds and tries again.

---

## Features

* **Real-Time WebSockets:** Bi-directional streaming with built-in auth and payload limits.
* **Semantic Vector Search:** Find memories based on context, not just keyword matches.
* **Auto Context Compression:** Long conversations get summarized in the background automatically.
* **Strict Validation:** Pydantic schemas enforce payload constraints so users can't blow up your CPU.
* **Interactive API Docs:** Swagger UI is available at `/docs` and ReDoc at `/redoc` for easy testing right in your browser.

---

## Prerequisites & Environment

You need Docker installed. You'll also need a free [OpenRouter API Key](https://openrouter.ai/) for the background summarizer.

Create a `.env` file in the root directory (you can copy `.env.example`):

```env
DATABASE_URL="postgresql+asyncpg://postgres:tiger@localhost:5433/chatdb"
ChatSum_API="your_openrouter_api_key_here"
APP_API_KEY="your_super_secret_key"
```

---

## Quickstart

### Docker (Recommended)
Spin up the Postgres vector database and the FastAPI server:
```bash
docker-compose up --build -d
```
Your Memory Engine is live at `http://127.0.0.1:8000`.

### Local Setup
If you already have a Postgres server with `pgvector` running:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## Examples

We provide a Python SDK for easy integration, but you can also interact via standard REST.

### 1. Save a Memory (POST)
```python
import httpx

httpx.post(
    "http://127.0.0.1:8000/chats/",
    headers={"X-API-Key": "your_super_secret_key"},
    json={
        "user_id": "user_123",
        "conversation_id": "thread_abc",
        "message": "I am allergic to peanuts."
    }
)
```

### 2. Retrieve Memory (GET)
```python
response = httpx.get(
    "http://127.0.0.1:8000/chats/thread_abc?page=1&limit=50",
    headers={"X-API-Key": "your_super_secret_key"}
)
print(response.json())
```

### 3. Stream (WebSocket)
```python
import websockets
import asyncio

async def stream():
    uri = "ws://127.0.0.1:8000/chats/ws/thread_abc?api_key=your_super_secret_key"
    async with websockets.connect(uri) as websocket:
        await websocket.send("Hello, engine.")
        print(await websocket.recv())

asyncio.run(stream())
```

---

## License & Liability

ContextFold is released under the [MIT License](LICENSE). 
*Disclaimer: ContextFold is provided "AS IS". Users are responsible for securing their own API keys, databases, and infrastructure. We don't host or intercept your data. The authors assume no liability for data loss or unexpected API token costs.*

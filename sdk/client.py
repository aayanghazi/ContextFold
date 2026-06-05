import httpx
import websockets
from urllib.parse import urlparse

class AIMemoryClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        # Instantiate httpx.AsyncClient with automatic auth header and timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            timeout=60.0
        )

    async def save_message(self, user_id: str, conversation_id: str, message: str) -> dict:
        """Saves a message to the specified conversation."""
        response = await self.client.post("/chats/", json={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message": message
        })
        response.raise_for_status()
        return response.json()

    async def get_history(self, conversation_id: str) -> dict:
        """Retrieves the history of a conversation."""
        response = await self.client.get(f"/chats/{conversation_id}")
        response.raise_for_status()
        return response.json()

    async def semantic_search(self, user_id: str, query: str) -> list:
        """Performs a semantic search across all chats for a specific user."""
        response = await self.client.get("/chats/semantic_search/", params={"user_id": user_id, "query": query})
        response.raise_for_status()
        return response.json()

    async def stream_chat(self, conversation_id: str):
        """Connects to the WebSocket endpoint for real-time streaming."""
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{scheme}://{parsed.netloc}{parsed.path}/chats/ws/{conversation_id}"
        
        # Returns the WebSocketClientProtocol
        # The caller should use this within an async context or explicitly manage it.
        return await websockets.connect(
            ws_url,
            additional_headers={"X-API-Key": self.api_key}
        )

    async def close(self):
        """Clean up the underlying httpx client."""
        await self.client.aclose()

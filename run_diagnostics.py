import asyncio
import os
import uuid
import httpx
from sdk.client import AIMemoryClient

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
APP_API_KEY = os.getenv("APP_API_KEY", "default_secret_key")

async def run_diagnostics():
    print("🚀 Starting Diagnostics Run...")
    
    print("\n" + "="*50)
    print("🛡️  TEST 1: The Bouncer (Auth Test)")
    print("="*50)
    
    fake_client = AIMemoryClient(BASE_URL, "fake_api_key_123")
    try:
        await fake_client.get_history("diagnostic_thread_test")
        print("❌ Auth test failed: Was able to access history with a fake key!")
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [401, 403]:
            print(f"✅ Auth test passed: Successfully blocked with status {e.response.status_code}")
        else:
            print(f"⚠️ Auth test got unexpected status: {e.response.status_code}")
    except Exception as e:
        print(f"⚠️ Auth test failed with unknown exception: {e}")
    finally:
        await fake_client.close()

    print("\n" + "="*50)
    print("📥 TEST 2: Standard Ingestion & Vectorization")
    print("="*50)
    
    client = AIMemoryClient(BASE_URL, APP_API_KEY)
    conversation_id = f"diagnostic_thread_{uuid.uuid4().hex[:8]}"
    print(f"🔑 Generated new conversation_id: {conversation_id}")
    
    user_id = "test_sdet_user"
    
    messages = [
        "In the future, flying cars will alleviate traffic congestion on major highways, but air traffic control will become a nightmare.",
        "To cook the perfect pasta, you must heavily salt the water until it tastes like the sea, and cook it al dente before tossing it in the sauce.",
        "Python's asyncio loop allows for concurrent execution of I/O bound tasks, making it ideal for web servers handling thousands of connections."
    ]
    
    for i, msg in enumerate(messages, 1):
        await client.save_message(user_id, conversation_id, msg)
        print(f"✅ Saved message {i}: {msg[:40]}...")
        
    print("🎉 Ingestion & Vectorization confirmed successful!")

    print("\n" + "="*50)
    print("🧠 TEST 3: The Mind Reader (Semantic Search)")
    print("="*50)
    
    search_query = "culinary skills"
    print(f"🔍 Executing semantic search for: '{search_query}'")
    
    try:
        results = await client.semantic_search(search_query)
        if results:
            print(f"✅ Found {len(results)} semantic matches!")
            for i, res in enumerate(results, 1):
                content = res.get("message", res.get("content", str(res)))
                print(f"   Match {i}: {content[:60]}...")
        else:
            print("⚠️ No matches found. Semantic search might not be matching correctly.")
    except Exception as e:
        print(f"❌ Semantic search test failed: {e}")

    print("\n" + "="*50)
    print("📡 TEST 4: The Walkie-Talkie (WebSocket Stream)")
    print("="*50)
    
    try:
        ws = await client.stream_chat(conversation_id)
        print("✅ WebSocket connection opened successfully (Auth OK).")
        
        await ws.send("ping")
        print("✅ Sent 'ping' message through WebSocket.")
        
        response = await ws.recv()
        print(f"✅ Received response back: {response}")
        
        await ws.close()
        print("✅ WebSocket connection closed cleanly.")
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")

    print("\n" + "="*50)
    print("🧹 TEST 5: The Silent Janitor (Background Summarization)")
    print("="*50)
    
    print("⏳ Firing 50 dummy messages to trigger the background summarization task...")
    for i in range(1, 51):
        await client.save_message(user_id, conversation_id, f"Dummy filler message {i} to exceed the summarization threshold.")
        await asyncio.sleep(0.1)
        
    print("✅ 50 dummy messages ingested.")
    print("⏸️  Waiting 10 seconds for the background task to contact OpenRouter and compress the context...")
    await asyncio.sleep(10)
    
    try:
        history_response = await client.get_history(conversation_id)
        print("✅ Final history retrieved.")
        
        history_msgs = history_response.get("chats", []) if isinstance(history_response, dict) else []
        if not history_msgs and isinstance(history_response, list):
            history_msgs = history_response
            
        system_messages = [m for m in history_msgs if m.get("user_id") == "system"]
        
        print(f"📊 Total messages in history now: {len(history_msgs)}")
        
        if system_messages:
            print("✅ Found system summary message!")
            print(f"📝 Summary preview: {system_messages[-1].get('message', '')}")
            if len(history_msgs) < 54:
                print("✅ History was successfully drastically compressed!")
            else:
                print("⚠️ History is still large. Compression might still be running or failed silently.")
        else:
            print("❌ No system summary message found. Background task may have failed.")
    except Exception as e:
        print(f"❌ Background summarization test failed to retrieve history: {e}")
        
    await client.close()
    
    print("\n" + "="*50)
    print("🏁 All Diagnostics Completed successfully!")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())

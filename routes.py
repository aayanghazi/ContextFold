import os
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, Security, BackgroundTasks, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, func
from database import get_db, SessionLocal
from models import ChatMessage
from pydantic import BaseModel, Field
from datetime import datetime
import asyncio
import time
from fastembed import TextEmbedding
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Initialize FastEmbed Model
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

async def generate_embedding(text: str):
    def embed_sync():
        return list(embedding_model.embed([text]))[0]
    return await asyncio.to_thread(embed_sync)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_openrouter_async(api_key: str, chat_text: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "ChatSummarizationAPI"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {"role": "system", "content": "Summarize the following conversation in 2-3 sentences."},
                    {"role": "user", "content": chat_text}
                ]
            }
        )
        response.raise_for_status()
        return response.json()

failed_summarizations_cooldown = {}
active_summarizations = set()

async def background_summarize_thread(conversation_id: str):
    if conversation_id in active_summarizations:
        return
    if conversation_id in failed_summarizations_cooldown:
        if time.time() - failed_summarizations_cooldown[conversation_id] < 300:
            return
            
    active_summarizations.add(conversation_id)
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.timestamp.asc())
                .limit(50)
            )
            chats = result.scalars().all()
            
            if len(chats) < 50:
                return
                
            tenant_user_id = chats[0].user_id
            chat_text = "\n".join([chat.message for chat in chats])
            
            try:
                load_dotenv()
                api_key = os.getenv("ChatSum_API") or os.getenv("CHATSUM_API")
                response_json = await call_openrouter_async(api_key, chat_text)
                if "error" in response_json:
                    print(f"Error in background summarization: {response_json['error']}")
                    return
                summary = response_json["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Exception in OpenRouter call: {str(e)}")
                failed_summarizations_cooldown[conversation_id] = time.time()
                return
                
            emb = await generate_embedding(summary)
            
            summary_chat = ChatMessage(
                user_id=tenant_user_id,
                conversation_id=conversation_id,
                message=summary,
                timestamp=datetime.utcnow(),
                embedding=emb
            )
            db.add(summary_chat)
            
            chat_ids = [chat.id for chat in chats]
            await db.execute(delete(ChatMessage).where(ChatMessage.id.in_(chat_ids)))
            await db.commit()
    finally:
        active_summarizations.remove(conversation_id)

load_dotenv()
OPENROUTER_API_KEY = os.getenv("CHATSUM_API")
if not OPENROUTER_API_KEY:
    raise RuntimeError("API Key not found. Check your .env file!")

APP_API_KEY = os.getenv("APP_API_KEY")
if not APP_API_KEY or APP_API_KEY in ("your_super_secret_key", "default_secret_key"):
    raise RuntimeError("CRITICAL FAILURE: APP_API_KEY is unset or insecure in .env file")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != APP_API_KEY:
        raise HTTPException(status_code=403, detail="Could not validate API KEY")
    return api_key

router = APIRouter()

class ChatCreate(BaseModel):
    user_id: str = Field(..., max_length=100)
    conversation_id: str = Field(..., max_length=100)
    message: str = Field(..., max_length=4000)

class SummarizeRequest(BaseModel):
    conversation_id: str

@router.post("/")
@limiter.limit("5/minute")
async def create_chat(request: Request, chat: ChatCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    emb = await generate_embedding(chat.message)
    new_chat = ChatMessage(
        user_id=chat.user_id,
        conversation_id=chat.conversation_id,
        message=chat.message,
        timestamp=datetime.utcnow(),
        embedding=emb
    )
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    
    count_result = await db.execute(select(func.count(ChatMessage.id)).filter(ChatMessage.conversation_id == chat.conversation_id))
    count = count_result.scalar()
    
    if count >= 50:
        background_tasks.add_task(background_summarize_thread, chat.conversation_id)
        
    return {
        "status": "success",
        "id": new_chat.id,
        "conversation_id": new_chat.conversation_id
    }

@router.post("/summarize")
async def summarize_chat(request: SummarizeRequest, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.conversation_id == request.conversation_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(100)
    )
    chats = result.scalars().all()

    if not chats:
        raise HTTPException(status_code=404, detail="No chats found for this conversation")

    chat_text = "\n".join([chat.message for chat in chats])

    try:
        load_dotenv()
        api_key = os.getenv("ChatSum_API") or os.getenv("CHATSUM_API")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "ChatSummarizationAPI"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {"role": "system", "content": "Summarize the following conversation in 2-3 sentences."},
                    {"role": "user", "content": chat_text}
                ]
            }
        )
        response_json = response.json()
        
        if "error" in response_json:
            raise HTTPException(status_code=502, detail=response_json["error"])
            
        summary = response_json["choices"][0]["message"]["content"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in summarization: {str(e)}")

    return {"conversation_id": request.conversation_id, "summary": summary}

@router.get("/search/")
async def search_chats(user_id: str = Query(..., description="Filter by user"), keyword: str = Query(..., description="Keyword to search in chats"), db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    import re
    safe_keyword = re.escape(keyword)
    result = await db.execute(
        select(ChatMessage).filter(ChatMessage.message.ilike(f"%{safe_keyword}%")).filter(ChatMessage.user_id == user_id)
    )
    chats = result.scalars().all()
    return [{"id": msg.id, "user_id": msg.user_id, "conversation_id": msg.conversation_id, "message": msg.message} for msg in chats]

@router.get("/semantic_search/")
async def semantic_search_chats(
    user_id: str = Query(..., description="Filter by user"),
    query: str = Query(..., description="Query for semantic search"),
    limit: int = Query(5, description="Number of results to return"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    emb = await generate_embedding(query)
    
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.embedding.cosine_distance(emb))
        .limit(limit)
    )
    chats = result.scalars().all()
    return [{"id": msg.id, "user_id": msg.user_id, "conversation_id": msg.conversation_id, "message": msg.message} for msg in chats]

@router.get("/users/{user_id}")
async def get_user_chats(
    user_id: str, 
    page: int = Query(1, ge=1, description="Page number"), 
    limit: int = Query(10, description="Items per page"), 
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    print(f"Fetching chats for user: {user_id}, page: {page}, limit: {limit}")
    
    offset = (page - 1) * limit
    
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    chats = result.scalars().all()

    total_chats_result = await db.execute(
        select(func.count(ChatMessage.id)).filter(ChatMessage.user_id == user_id)
    )
    total_chats = total_chats_result.scalar()

    return {
        "user_id": user_id,
        "page": page,
        "limit": limit,
        "total_chats": total_chats,
        "total_pages": (total_chats // limit) + (1 if total_chats % limit > 0 else 0),
        "chats": chats
    }

@router.get("/{conversation_id}")
async def get_chats(
    conversation_id: str, 
    page: int = Query(1, ge=1, description="Page number"), 
    limit: int = Query(50, description="Items per page"), 
    db: AsyncSession = Depends(get_db), 
    api_key: str = Depends(get_api_key)
):
    offset = (page - 1) * limit
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.timestamp.asc())
        .offset(offset)
        .limit(limit)
    )
    chats = result.scalars().all()
    
    if not chats:
        return {"message": "No chats found for this conversation"}
    
    clean_chats = [{"id": msg.id, "user_id": msg.user_id, "conversation_id": msg.conversation_id, "message": msg.message} for msg in chats]
    return {"conversation_id": conversation_id, "page": page, "limit": limit, "chats": clean_chats}

@router.delete("/{chat_id}")
async def delete_chat(chat_id: int, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(select(ChatMessage).filter(ChatMessage.id == chat_id))
    chat = result.scalars().first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    await db.execute(delete(ChatMessage).where(ChatMessage.id == chat_id))
    await db.commit()

    return {"message": f"Chat {chat_id} deleted successfully"}

@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    # Authenticate WebSocket before accepting
    api_key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    if api_key != APP_API_KEY:
        await websocket.close(code=1008, reason="Could not validate API KEY")
        return
    await websocket.accept()
    last_message_time = 0.0
    try:
        while True:
            data = await websocket.receive_text()
            current_time = time.time()
            if current_time - last_message_time < 0.5:
                await websocket.send_text("Error: Rate limit exceeded. Please slow down.")
                continue
            last_message_time = current_time
            if len(data) > 2000:
                await websocket.send_text("Error: Message exceeds maximum length of 2000 characters.")
                continue
                
            print(f"Message received for conversation {conversation_id}: {data}")
            
            async with SessionLocal() as db:
                # Generate embedding and save to database
                try:
                    emb = await generate_embedding(data)
                    new_chat = ChatMessage(
                        user_id="websocket_user", 
                        conversation_id=conversation_id,
                        message=data,
                        timestamp=datetime.utcnow(),
                        embedding=emb
                    )
                    db.add(new_chat)
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    await websocket.send_text(f"Internal error processing message: {str(e)}")
                    continue
                
                count_result = await db.execute(select(func.count(ChatMessage.id)).filter(ChatMessage.conversation_id == conversation_id))
                count = count_result.scalar()
                
                if count >= 50:
                    asyncio.create_task(background_summarize_thread(conversation_id))
            
            await websocket.send_text(f"Message confirmed: {data}")
    except WebSocketDisconnect:
        print(f"Client gracefully disconnected from conversation {conversation_id}")

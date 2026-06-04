from sqlalchemy import Column, Integer, String, Text, DateTime, func, Index
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class ChatMessage(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    conversation_id = Column(String, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    embedding = Column(Vector(384))

    __table_args__ = (
        Index(
            'ix_chats_embedding_hnsw', 
            'embedding', 
            postgresql_using='hnsw', 
            postgresql_with={'m': 16, 'ef_construction': 64}, 
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
    )

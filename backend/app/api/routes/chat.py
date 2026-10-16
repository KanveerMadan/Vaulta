"""
Chat assistant.

  POST   /api/chat           {message, session_id?} → {reply, session_id, tables, actions, tools_used}
  POST   /api/chat/confirm   {token, decision: confirm|cancel} — the only way an action runs
  GET    /api/chat/history   ?session_id=… last 10 turns
  DELETE /api/chat/history   ?session_id=… (omit to clear all)
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse, HistoryItem
from app.services import chat
from app.services import activity

router = APIRouter(prefix="/api/chat", tags=["chat"])


def chat_enabled(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.ai_chat_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is turned off in settings.")
    return current_user


@router.post("", response_model=ChatResponse)
def send(payload: ChatRequest, user: User = Depends(chat_enabled), db: Session = Depends(get_db)):
    try:
        return chat.handle_message(db, user, payload.message.strip(), payload.session_id)
    except chat.ChatLimit as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))


@router.post("/confirm", response_model=ConfirmResponse)
def confirm(payload: ConfirmRequest, user: User = Depends(chat_enabled), db: Session = Depends(get_db)):
    try:
        return chat.resolve_action(db, user, payload.token, payload.decision == "confirm")
    except chat.ActionUnavailable as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))


@router.get("/history", response_model=List[HistoryItem])
def get_history(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [HistoryItem(role=m.role, content=m.content) for m in chat.history(db, user, session_id)]


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(session_id: Optional[uuid.UUID] = Query(default=None), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = db.query(ChatMessage).filter(ChatMessage.user_id == user.id)
    if session_id:
        q = q.filter(ChatMessage.session_id == session_id)
    q.delete(synchronize_session=False)
    activity.record(db, user, "deleted", {"what": "chat history"})
    db.commit()

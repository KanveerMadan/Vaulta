"""
Review queue ("Needs review" cards).

  GET  /api/review                     cards, most important first, and the count for the badge
  POST /api/review/{card_id}/answer    {"answer": <option value>} — applies it ("skip" hides the card)
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.review import ReviewAnswer, ReviewCardResponse, ReviewQueue
from app.services.review import answer_card, build_cards

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("", response_model=ReviewQueue)
def get_queue(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cards = build_cards(db, current_user)
    return ReviewQueue(count=len(cards), items=[ReviewCardResponse.model_validate(c, from_attributes=True) for c in cards])


@router.post("/{card_id}/answer", response_model=ReviewQueue)
def answer(
    payload: ReviewAnswer,
    card_id: str = Path(pattern=r"^[a-z]+:[A-Za-z0-9 &-]{1,100}$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = next((c for c in build_cards(db, current_user) if c.id == card_id), None)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That question is no longer open.")
    if payload.answer not in {o["value"] for o in card.options}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Not one of the options.")
    answer_card(db, current_user, card, payload.answer)
    return get_queue(current_user, db)

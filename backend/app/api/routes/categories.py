"""
The category taxonomy, the user's own subcategories, and tags.

  GET    /api/categories                      groups → subcategories (taxonomy + the user's own)
  POST   /api/categories/subcategories        {group, name}: add your own subcategory to a group
  DELETE /api/categories/subcategories/{id}   remove it; its transactions keep the group, its budgets end
  GET    /api/tags                            your tags with how many transactions carry each
  DELETE /api/tags/{id}                       remove a tag from every transaction
  POST   /api/categories/recategorise         {"dry_run": true}: what re-checking with the current categoriser would
                                              change; {"dry_run": false}: apply it (services/recategorise.py)
  POST   /api/categories/recategorise/{id}/undo   put a run's previous automatic categories back
Tags are set on a transaction with PATCH /api/transactions/{id} {"tags": [...]}.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.category import CustomSubcategory, Tag, TransactionTag
from app.models.user import User
from app.models.categorizer import RecategorisationRun
from app.services import categories, recategorise, taxonomy
from app.services.detection import run_detection

router = APIRouter(tags=["categories"])


class SubcategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    group: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=categories.MAX_NAME)


def _tree(db: Session, user: User) -> dict:
    custom = categories.custom_subcategories(db, user.id).values()
    groups = []
    for g in taxonomy.TAXONOMY["groups"]:
        subs = [{"id": s["id"], "name": s["name"], "definition": s["definition"]} for s in g["subcategories"]]
        subs += [{"id": c.key, "name": c.name, "custom": True}
                 for c in sorted(custom, key=lambda c: c.name.lower()) if c.group == g["name"]]
        groups.append({"name": g["name"], "credit_only": bool(g.get("credit_only")), "subcategories": subs})
    return {"groups": groups, "system_groups": taxonomy.SYSTEM_GROUPS}


@router.get("/api/categories")
def get_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _tree(db, user)


@router.post("/api/categories/subcategories", status_code=status.HTTP_201_CREATED)
def add_subcategory(payload: SubcategoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = categories.create_subcategory(db, user, payload.group, payload.name)
    except categories.CategoryError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return {"id": row.key, "name": row.name, "group": row.group, "custom": True}


@router.delete("/api/categories/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_subcategory(subcategory_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(CustomSubcategory).filter(CustomSubcategory.id == subcategory_id, CustomSubcategory.user_id == user.id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found.")
    categories.delete_subcategory(db, user, row)
    run_detection(db, user)


class RecategoriseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dry_run: bool = True


@router.post("/api/categories/recategorise")
def recategorise_all(payload: RecategoriseRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.dry_run:
        return recategorise.dry_run(db, user)
    run = recategorise.apply(db, user)
    return {"run_id": str(run.id), "changed": run.changed, "summary": run.summary}


@router.post("/api/categories/recategorise/{run_id}/undo")
def undo_recategorise(run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.query(RecategorisationRun).filter(RecategorisationRun.id == run_id, RecategorisationRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return {"restored": recategorise.undo(db, user, run)}


@router.get("/api/tags")
def list_tags(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    counts = dict(db.query(TransactionTag.tag_id, func.count()).filter(TransactionTag.user_id == user.id)
                  .group_by(TransactionTag.tag_id).all())
    tags = db.query(Tag).filter(Tag.user_id == user.id).all()
    return {"items": sorted(({"id": str(t.id), "name": t.name, "count": counts.get(t.id, 0)} for t in tags),
                            key=lambda t: t["name"].lower())}


@router.delete("/api/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user.id).first()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    db.delete(tag)
    db.commit()

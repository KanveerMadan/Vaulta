"""Writing goals and contributions (the numbers come from analytics.goal_status)."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalEntry
from app.models.user import User


def create_goal(db: Session, user: User, name: str, target_amount: Decimal, target_date: date,
                category: Optional[str] = None) -> Goal:
    goal = Goal(user_id=user.id, name=name.strip(), target_amount=target_amount, target_date=target_date, category=category)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def add_entry(db: Session, goal: Goal, amount: Decimal, day: date) -> GoalEntry:
    entry = GoalEntry(goal_id=goal.id, user_id=goal.user_id, amount=amount, entry_date=day)
    db.add(entry)
    db.commit()
    db.refresh(goal)
    return entry


def find_goal(db: Session, user: User, name: str) -> list[Goal]:
    """Goals whose name matches exactly (case-insensitive), else contains `name`."""
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    needle = name.strip().lower()
    return [g for g in goals if g.name.lower() == needle] or [g for g in goals if needle and needle in g.name.lower()]

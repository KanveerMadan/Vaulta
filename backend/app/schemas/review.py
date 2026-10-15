from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ReviewOption(BaseModel):
    value: str
    label: str


class ReviewCardResponse(BaseModel):
    id: str
    type: str
    question: str
    detail: str
    options: List[ReviewOption]


class ReviewQueue(BaseModel):
    count: int
    items: List[ReviewCardResponse]


class ReviewAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str = Field(min_length=1, max_length=40)

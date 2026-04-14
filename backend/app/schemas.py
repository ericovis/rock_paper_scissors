from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Choice = Literal["rock", "paper", "scissors"]
WinnerSymbol = Literal["you", "opponent", "draw"]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)


class UserResponse(BaseModel):
    user_id: int
    username: str


class CreateRoomResponse(BaseModel):
    room_id: int
    share_url: str


class OpenRoom(BaseModel):
    room_id: int
    creator_username: str
    created_at: datetime


class RoomDetails(BaseModel):
    room_id: int
    player_1_username: str
    player_2_username: str | None
    created_at: datetime
    ended_at: datetime | None


class LeaderboardEntry(BaseModel):
    user_id: int
    username: str
    wins: int


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]


# ----- WebSocket events -----


class WSMessage(BaseModel):
    event: str
    data: dict = Field(default_factory=dict)


class SubmitChoiceData(BaseModel):
    choice: Choice


class RoundResultScore(BaseModel):
    you: int
    opponent: int


class RoundResultData(BaseModel):
    round_number: int
    your_choice: Choice | None
    opponent_choice: Choice | None
    winner: WinnerSymbol
    score: RoundResultScore

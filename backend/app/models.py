from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: int
    username: str
    created_at: datetime


@dataclass
class GameRoom:
    id: int
    player_1_id: int
    player_2_id: int | None
    created_at: datetime
    ended_at: datetime | None


@dataclass
class Round:
    id: int
    game_room_id: int
    round_number: int
    player_1_choice: str | None
    player_2_choice: str | None
    winner_id: int | None
    played_at: datetime

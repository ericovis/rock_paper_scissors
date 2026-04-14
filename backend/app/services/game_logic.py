from typing import Literal

Choice = Literal["rock", "paper", "scissors"]
RoundWinner = Literal["p1", "p2", "draw"]

BEATS: dict[str, str] = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper",
}


def resolve_round(c1: Choice | None, c2: Choice | None) -> RoundWinner:
    if c1 is None and c2 is None:
        return "draw"
    if c1 is None:
        return "p2"
    if c2 is None:
        return "p1"
    if c1 == c2:
        return "draw"
    return "p1" if BEATS[c1] == c2 else "p2"

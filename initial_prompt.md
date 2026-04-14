# Rock Paper Scissors

A real-time, 1v1 Rock Paper Scissors web game with animated 3D visuals, persistent game rooms, and a global leaderboard.

---

## Project Structure

```
rock_paper_scissors/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI entry point (lifespan: pool, schema, leaderboard rebuild)
│       ├── models.py            # Row dataclasses (User, GameRoom, Round)
│       ├── schemas.py           # Pydantic request/response + WS event schemas
│       ├── schema.sql           # DB schema, bootstrapped on startup
│       ├── routers/
│       │   ├── users.py         # REST: user creation & lookup
│       │   ├── rooms.py         # REST: room creation & listing
│       │   ├── leaderboard.py   # REST: leaderboard query
│       │   └── game.py          # WebSocket: game room handler
│       ├── services/
│       │   ├── game_logic.py    # Round resolution, timeout, scoring
│       │   └── room_manager.py  # Redis-backed room state, in-process socket fan-out
│       └── db.py                # psycopg3 AsyncConnectionPool + get_conn() helper
└── frontend/
    ├── Dockerfile
    ├── package.json             # Vite + three
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js              # Entry point
        ├── scene/               # three.js scene, hand models, animations
        ├── ui/                  # Lobby, scoreboard, overlays
        ├── ws.js                # WebSocket client wrapper
        └── state.js             # Client-side game state
```

---

## Architecture

### Backend

- **Language:** Python
- **Web framework:** FastAPI
- **Database:** PostgreSQL via raw psycopg3 (`AsyncConnectionPool`) with hand-written parameterised SQL — stores users, game rooms, round history, and leaderboard data. No ORM. Schema is bootstrapped from `schema.sql` on startup (no Alembic for MVP).
- **Cache / real-time state:** Redis — holds in-game state (current round, pending choices, connection flags, server-authoritative deadline) and the leaderboard sorted set. **No pub/sub for MVP** — a single FastAPI process does in-process asyncio fan-out to connected sockets. Pub/sub can be added later if the backend is horizontally scaled.

### Frontend

- **Rendering:** three.js — animated 3D hand models for rock, paper, and scissors gestures
- **Communication:** WebSocket connection to the backend for live game state updates; REST calls for user creation, room listing, and leaderboard

### Communication Flow

```
Browser (three.js + WS client)
        ↕  WebSocket + REST
FastAPI server
        ↕               ↕
     Redis            PostgreSQL
  (live state)     (persistent data)
```

---

## User Identity

- On first visit the player is prompted to choose a **username**.
- The server creates a User record and returns the **user ID**.
- The user ID is stored in a long-lived cookie named **`rps_user_id`** with attributes `HttpOnly`, `SameSite=Lax`, `Secure` in production, `Max-Age=315360000` (10 years). Subsequent HTTP requests and WebSocket handshakes include it to identify the player.
- No email, password, or OAuth is required — the cookie **is** the identity.
- If the cookie is lost the player simply creates a new username; previous stats are not recoverable (acceptable trade-off for simplicity).

---

## Game Workflow

### Lobby (Main Page)

1. Player lands on the main page and sees:
   - A **list of open game rooms** they can join.
   - A **"Create Room"** button to start a new room.
   - The **global leaderboard** (ranked by total wins).
2. When creating a room the player receives a **shareable link** they can send to a friend. `POST /api/rooms` inserts a `GameRoom` row with `player_1_id = <cookie user>`, `player_2_id = NULL`, `ended_at = NULL`, and returns `{ room_id, share_url }`.
3. A room requires exactly **2 players** (1v1). The second player is claimed atomically on WebSocket connect via `UPDATE game_room SET player_2_id = %s WHERE id = %s AND player_2_id IS NULL RETURNING player_1_id` — this wins the race or the server closes the socket with an `error` frame (`room_full` / `room_ended`). Once both seats are filled the game begins.

### Game Room

- A game room supports **unlimited rounds** — players keep playing until one of them leaves.
- Each round follows the **simultaneous-reveal** model:
  1. Both players privately select rock, paper, or scissors.
  2. Once both choices are submitted, the result is revealed to both players at the same time.
  3. If a player has not submitted a choice yet, the other player sees a "waiting" state.
- The room displays a **running score** for the session, e.g. *PlayerX 1 — 5 PlayerY*.
- Every round result is persisted so it contributes to the global leaderboard.

### End of Session

- A session ends when a player **explicitly leaves** (sends `leave_room`) or when the 10-second reconnect grace (below) expires.
- On session end, the `GameRoom` row is stamped with `ended_at = now()` and the remaining player is notified via `opponent_left` and returned to the lobby. Rooms are never reopened.

### Disconnection Handling

- Any unexpected WebSocket drop — including the player closing the tab or browser — starts a **10-second reconnect grace**. The opponent is notified immediately via `opponent_disconnected { grace_seconds: 10 }`.
- The reconnecting client is identified by the `rps_user_id` cookie on the new WebSocket handshake plus the `room_id` in the URL. If it matches a participant of the room, the game resumes from the current round state and the opponent receives `opponent_reconnected`.
- If the player does not reconnect within the window, it is treated as leaving — the session ends and the opponent is notified via `opponent_left`.
- The client does **not** need a `beforeunload` hook — browser close is just another drop.

---

## Data Model (High-Level)

| Entity       | Key Fields                                           | Storage    |
|------------- |------------------------------------------------------|------------|
| **User**     | `id`, `username`, `created_at`                       | PostgreSQL |
| **GameRoom** | `id`, `player_1_id` (NOT NULL), `player_2_id` (nullable until the second player joins), `created_at`, `ended_at` (nullable until the session ends) | PostgreSQL |
| **Round**    | `id`, `game_room_id`, `player_1_choice` (nullable — `null` = forfeit), `player_2_choice` (nullable — `null` = forfeit), `winner_id` (nullable — `null` = draw), `played_at` | PostgreSQL |
| **RoomState**| round number, server-authoritative deadline (unix ms), pending choices, per-player connection flags | Redis      |

A room is considered **open** (joinable, listed by `GET /api/rooms`) when `player_2_id IS NULL AND ended_at IS NULL`. There is no separate `status` column — the nullable columns are the source of truth.

---

## Leaderboard

- Displayed on the main page.
- Ranked by **total wins** across all game rooms.
- Backed by a **Redis sorted set** at key `leaderboard:wins` with **`user_id` as the member** (stable; a username cache maps id → username for rendering). `ZINCRBY leaderboard:wins 1 <user_id>` is called on each round win (forfeit wins count too).
- PostgreSQL is the source of truth. On startup the sorted set is rebuilt via `SELECT winner_id, count(*) FROM round WHERE winner_id IS NOT NULL GROUP BY winner_id`.

---

## Frontend / 3D Visuals

### Lobby UI

- Clean, minimal layout: room list on the left, leaderboard on the right, "Create Room" button centered.
- Each room entry shows the creator's username and a "Join" button.
- Leaderboard shows top players by total wins.

### Game Room Scene

- **three.js scene** renders two animated hand models facing each other.
- During the selection phase each player sees their own hand in a "ready" pose.
- On reveal, both hands animate into the chosen gesture (rock fist, paper open hand, scissors).
- A brief highlight / effect indicates the round winner.
- A **countdown timer bar** (45 s) is visible at the top of the scene.
- The UI also shows the running score, opponent's username, and a button to leave the room.

---

## WebSocket Protocol

The WebSocket URL is `/ws/game/{room_id}`. The room is known from the URL and the player is known from the `rps_user_id` cookie on the handshake, so neither is repeated in message payloads. All messages are JSON with a top-level `event` and `data` field.

### Client → server

| Event           | Payload                                         | Description                         |
|-----------------|-------------------------------------------------|-------------------------------------|
| `submit_choice` | `{ choice: "rock" \| "paper" \| "scissors" }`  | Player submits a choice for the current round. |
| `leave_room`    | `{}`                                            | Explicit leave — ends the session immediately. |

### Server → client

| Event                    | Payload                                                                                                     | Description                                                                 |
|--------------------------|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `room_ready`             | `{ opponent_username }`                                                                                     | Both players are present, game can start.                                   |
| `round_start`            | `{ round_number, deadline_unix_ms }`                                                                        | New round begins. `deadline_unix_ms` is the server-authoritative cutoff; the client renders the countdown against it (and its own clock for smoothness), eliminating clock-skew bugs. |
| `opponent_submitted`     | `{}`                                                                                                        | Opponent has locked in (no reveal yet).                                     |
| `round_result`           | `{ round_number, your_choice, opponent_choice, winner, score }`                                             | Round resolved. `your_choice` and `opponent_choice` are `"rock" \| "paper" \| "scissors" \| null` (null means that player timed out). `winner` is `"you" \| "opponent" \| "draw"` — symbolic per recipient, so the client never maps user ids. `score` is `{ you: number, opponent: number }`. |
| `opponent_disconnected`  | `{ grace_seconds: 10 }`                                                                                     | Opponent dropped — waiting for reconnect within the grace window.           |
| `opponent_reconnected`   | `{}`                                                                                                        | Opponent reconnected within the grace window; game resumes.                 |
| `opponent_left`          | `{}`                                                                                                        | Opponent left explicitly or the grace window expired — session ended.       |
| `error`                  | `{ code, message }`                                                                                         | Error frame before the socket closes, e.g. `room_full`, `room_ended`, `not_a_participant`. |

Notes:
- There is no `join_room` client event — joining happens implicitly on WebSocket connect.
- There is no `timeout_forfeit` event — timeouts are delivered through `round_result` with one or both choices set to `null`.

---

## Round Timeout

- Each player has **45 seconds** to submit their choice once a new round starts.
- The authoritative cutoff is the server-side `deadline_unix_ms` sent in `round_start`; the client renders a countdown bar against it.
- If a player fails to submit before the deadline, the round is resolved with that player's choice set to `null`:
  - One player submitted, the other timed out → the submitter wins (forfeit).
  - Both timed out → the round is a **draw**.
- Either way, the resolution is delivered via `round_result` (nullable choices), not a dedicated event. The `Round` row is persisted with the corresponding nullable `player_n_choice`.

---

## Mobile Support

- **Detection:** mobile mode is activated when `matchMedia('(pointer: coarse)').matches` **and** viewport width is below 768 px.
- **Lobby / Main Page:** Responsive layout — adapts to any screen size using standard responsive CSS.
- **Game Room:** Dedicated touch-based mobile view:
  - Large, tap-friendly buttons for rock / paper / scissors selection.
  - Simplified three.js scene: lower-poly hand models, no shadow maps, no post-processing, a single directional light, and `renderer.pixelRatio = 1`.
  - Gesture feedback (e.g. haptic / visual pulse on tap).
  - Score and timer prominently displayed at the top.

---

## Local Development (Docker Compose)

A `docker-compose.yml` at the project root spins up the full stack locally.

### Services

| Service        | Image / Build              | Ports          | Notes                                        |
|----------------|----------------------------|----------------|----------------------------------------------|
| **backend**    | Build from `./backend`     | `8000:8000`    | FastAPI with hot-reload (`--reload`)         |
| **frontend**   | Build from `./frontend`    | `5173:5173`    | Vite dev server with HMR (three.js app)      |
| **postgres**   | `postgres:18-alpine`              | `5432:5432`    | Persistent volume for data                   |
| **redis**      | `redis:8`                  | `6379:6379`    | Ephemeral (no persistence needed for dev)    |

### Volume Mounts

- `./backend` is mounted into the backend container so code changes are reflected **live** (FastAPI `--reload` watches for file changes).
- `./frontend` is mounted into the frontend container so the dev server picks up changes via **HMR**.
- A named volume is used for PostgreSQL data so it survives container restarts.

### Typical Workflow

```bash
# Start the full stack
docker compose up

# Rebuild after dependency changes
docker compose up --build

# Tear down (preserves DB volume)
docker compose down

# Tear down and wipe DB
docker compose down -v
```

---

## REST API Endpoints

| Method | Path                  | Description                                                                                  | Auth        |
|--------|-----------------------|----------------------------------------------------------------------------------------------|-------------|
| POST   | `/api/users`          | Create a new user; sets the `rps_user_id` cookie and returns `{ user_id, username }`         | None        |
| GET    | `/api/users/me`       | Get current user info from cookie                                                            | Cookie      |
| POST   | `/api/rooms`          | Create a new game room (creator becomes `player_1`); returns `{ room_id, share_url }`        | Cookie      |
| GET    | `/api/rooms`          | List open rooms — `WHERE player_2_id IS NULL AND ended_at IS NULL ORDER BY created_at DESC`  | None        |
| GET    | `/api/rooms/{room_id}`| Get room details and status                                                                  | None        |
| GET    | `/api/leaderboard`    | Top players by total wins (reads the Redis sorted set, joins usernames from the cache)      | None        |
| WS     | `/ws/game/{room_id}`  | WebSocket connection for gameplay                                                             | Cookie      |

---

## Open Questions / Future Considerations

- **Spectator mode:** Allow others to watch an ongoing match?
- **Rematch flow:** Quick "play again" button after someone leaves?
- **Variants:** Expand to Rock Paper Scissors Lizard Spock or custom rule sets?


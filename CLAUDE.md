# CLAUDE.md

Orientation for future Claude sessions. The human-facing spec lives in [initial_prompt.md](initial_prompt.md) — read it first for product intent. This file captures the non-obvious stuff that isn't visible from reading the code cold.

## Stack at a glance

- **Backend:** FastAPI + raw psycopg3 (no ORM) + redis-py async. Single process. Python 3.13.
- **Frontend:** Vite + vanilla JS + three.js. No framework. No bundler config beyond `vite.config.js`.
- **Infra:** `docker compose up` brings up postgres, redis, backend (`--reload`), frontend (HMR). Postgres and frontend source are bind-mounted, so code edits hot-reload without a rebuild.

## Running it

```bash
docker compose up --build     # first time
docker compose up             # subsequent
docker compose down           # stop (keeps DB volume)
docker compose down -v        # stop + wipe DB
docker compose logs -f backend
```

Smoke test inside the backend container (has `websockets` installed already):

```bash
docker compose exec backend python -c "…"   # see the session where this was first run
```

There is **no pytest suite yet** — verification is manual via `curl` + a scripted WS client.

## Architectural decisions you need to know before editing

### 1. Raw psycopg3, no SQLAlchemy
All queries are hand-written parameterised SQL (`%s` placeholders) in the routers and services. [backend/app/db.py](backend/app/db.py) owns a single `AsyncConnectionPool`; everything grabs a connection via `async with get_conn() as conn:`. Schema lives in [backend/app/schema.sql](backend/app/schema.sql) and is bootstrapped on startup in the FastAPI lifespan. **Do not add SQLAlchemy** — this was a deliberate choice. If you need migrations, add a small numbered-SQL-files runner, not Alembic.

Tables use `app_user` (not `user` — that's a Postgres reserved word).

### 2. Identity = a long-lived cookie
The cookie is `rps_user_id`, value is the integer user id, 10-year max-age, `HttpOnly`, `SameSite=Lax`, `Secure` only when `COOKIE_SECURE=true`. Set in [backend/app/auth.py](backend/app/auth.py); read on REST via `Depends(current_user_id)` and on WebSocket via `websocket.cookies.get(COOKIE_NAME)` in [backend/app/routers/game.py](backend/app/routers/game.py). There is no session table — losing the cookie means losing the identity, and that's intentional.

### 3. Game session state: in-memory *and* Redis
Live rooms are tracked in `_sessions: dict[int, RoomSession]` in [backend/app/services/room_manager.py](backend/app/services/room_manager.py). The in-memory session owns WebSocket references, asyncio timer tasks, and a per-room `asyncio.Lock`. Redis mirrors the *data* (round number, deadline, pending choices, score) in a hash keyed by `room:{id}` so the spec's promise of Redis-backed state is honored, but the authoritative source during a single process's lifetime is the in-memory session. **If you ever add a second backend replica**, Redis must become authoritative and the in-memory map becomes a per-replica cache + subscription target. That refactor is non-trivial — don't start it without a clear reason.

Per-room lock discipline: every state-changing operation takes `session.lock` for the whole critical section, including websocket sends. That's fine because there's at most one active round per room. Do not hold `_sessions_lock` (the module-level dict lock) while doing async I/O — it's only for dict add/remove.

### 4. `round_result` is the *only* round-end event
There is no `timeout_forfeit`. Timeouts are delivered via `round_result` with `your_choice`/`opponent_choice` set to `null` and `winner` set symbolically. The client never sees raw user ids on round outcomes — it sees `"you" | "opponent" | "draw"`. When adding new round-end logic, emit `round_result` and the client code in [frontend/src/ui/game_room.js](frontend/src/ui/game_room.js) will render it correctly.

### 5. Disconnect handling is unified
Any unexpected WS drop (network, tab close, browser quit) starts a **10-second reconnect grace** via `_grace_watcher` in room_manager. Only an explicit `leave_room` message ends the session immediately. The client does **not** use `beforeunload` — don't add it.

On reconnect within the grace window, the client re-enters via the same WS endpoint and is reattached to its existing slot (matched by user id). The session sends `opponent_reconnected` to the other player and re-sends `room_ready` + `round_start` to the reconnecting client so their timer can resume. Full score hydration on reconnect is **not** implemented — score catches up on the next `round_result`.

### 6. Player slot assignment
- `player_1` is set at `POST /api/rooms` (REST, requires cookie).
- `player_2` is claimed atomically on WebSocket connect via `UPDATE game_room SET player_2_id = %s WHERE id = %s AND player_2_id IS NULL RETURNING player_1_id`. If 0 rows are updated, the room is full or ended and the server sends an `error` frame and closes the socket.
- "Open room" is *derived*: `WHERE player_2_id IS NULL AND ended_at IS NULL`. There is no `status` column — don't add one.

### 7. Leaderboard
Redis sorted set `leaderboard:wins` keyed by `user_id` (not username, for stability across username changes we don't yet support). A hash `leaderboard:usernames` maps id → username for rendering. On startup, [backend/app/routers/leaderboard.py](backend/app/routers/leaderboard.py#L22) (`rebuild_leaderboard`) rebuilds both from Postgres — Postgres is the source of truth. Forfeit wins count.

## WebSocket protocol cheat sheet

URL: `/ws/game/{room_id}`. Cookie `rps_user_id` is required. Messages are JSON `{event, data}`.

**Client → server:** `submit_choice {choice}`, `leave_room {}`. There is no `join_room` — joining happens implicitly on connect.

**Server → client:** `room_ready`, `round_start`, `opponent_submitted`, `round_result`, `opponent_disconnected`, `opponent_reconnected`, `opponent_left`, `error`.

See [initial_prompt.md](initial_prompt.md#websocket-protocol) for the full payload table. The server-authoritative timer value is `deadline_unix_ms` in `round_start` — **never** send a duration like `timeout_seconds`, clients render the countdown against that absolute deadline to avoid clock skew.

## Frontend notes

- No framework. Views are imperative DOM functions in [frontend/src/ui/](frontend/src/ui/) that take `root` and return a teardown callback. Routing is a single `route()` function in [frontend/src/main.js](frontend/src/main.js) that reads `?room=<id>` from the URL.
- All HTTP requests include `credentials: 'include'` — this is required for the cookie to flow. Don't remove it.
- The three.js scene in [frontend/src/scene/scene.js](frontend/src/scene/scene.js) builds hand gestures from primitives (spheres, boxes, cylinders), not imported GLB models. If you add real art, keep the `createScene` / `setPhase` / `playReveal` / `dispose` interface so `game_room.js` doesn't need changes.
- Mobile detection is `matchMedia('(pointer: coarse)')` + viewport width < 768. On mobile: `pixelRatio=1`, no shadows, no fill light, lower-poly primitives. See [frontend/src/state.js](frontend/src/state.js#L14).

## Common gotchas

- **Postgres reserved word:** the users table is `app_user`, not `user`. Don't rename.
- **Cookie name:** `rps_user_id`, not `user_id` or `session_id`. Hardcoded in `auth.py`, `game.py`, and the CORS `allow_credentials=True` middleware.
- **CORS:** only `FRONTEND_ORIGIN` is allowed; `allow_credentials=True` means you can't use `*`. If you add a new frontend origin (e.g. a mobile web view), add it explicitly.
- **psycopg pool + transactions:** `async with pool.connection()` does **not** auto-commit. Writes must `await conn.commit()`. Reads can skip it; the pool rolls back on return.
- **FastAPI `--reload`** watches `/app` inside the container (bind-mounted from `./backend`). Editing a Python file triggers a full app restart, which drops in-memory sessions. In practice this only bites during active development — tell testers to not edit files mid-session.
- **Redis async pipeline:** use `pipe = r.pipeline()` then `await pipe.execute()`. Don't wrap in `async with`.

## Where to add things

- **New REST endpoint:** new file under [backend/app/routers/](backend/app/routers/), register in [backend/app/main.py](backend/app/main.py). Use `Depends(current_user_id)` if it needs auth.
- **New WS event:** add handler in `serve()` / `_handle_submit` etc. in [room_manager.py](backend/app/services/room_manager.py) and a matching branch in [frontend/src/ui/game_room.js](frontend/src/ui/game_room.js).
- **Schema change:** edit [backend/app/schema.sql](backend/app/schema.sql). Since `CREATE TABLE IF NOT EXISTS` won't alter existing tables, developers need to `docker compose down -v` to pick up changes. If that becomes painful, add a migration runner — but don't reach for Alembic.
- **New Pydantic schema:** [backend/app/schemas.py](backend/app/schemas.py) holds REST request/response bodies and the WS event payload models.

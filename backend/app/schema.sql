CREATE TABLE IF NOT EXISTS app_user (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS game_room (
    id           BIGSERIAL PRIMARY KEY,
    player_1_id  BIGINT NOT NULL REFERENCES app_user(id),
    player_2_id  BIGINT REFERENCES app_user(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS game_room_open_idx
    ON game_room (created_at DESC)
    WHERE player_2_id IS NULL AND ended_at IS NULL;

CREATE TABLE IF NOT EXISTS round (
    id               BIGSERIAL PRIMARY KEY,
    game_room_id     BIGINT NOT NULL REFERENCES game_room(id) ON DELETE CASCADE,
    round_number     INTEGER NOT NULL,
    player_1_choice  TEXT,
    player_2_choice  TEXT,
    winner_id        BIGINT REFERENCES app_user(id),
    played_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_room_id, round_number)
);

CREATE INDEX IF NOT EXISTS round_winner_idx ON round (winner_id) WHERE winner_id IS NOT NULL;

"""Apply incremental schema migrations for existing databases."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


MIGRATIONS = [
    "ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_name_key",
    "ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_code_key",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS tournament_id INTEGER REFERENCES tournaments(id)",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id)",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS flag_code VARCHAR(10)",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS confederation VARCHAR(20)",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS group_position INTEGER",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS tournament_id INTEGER REFERENCES tournaments(id)",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS stadium_id INTEGER REFERENCES stadiums(id)",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS kickoff_time_utc TIMESTAMPTZ",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS match_number INTEGER",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS matchday INTEGER",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS stage_order INTEGER DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS feeder_a_match_number INTEGER",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS feeder_b_match_number INTEGER",
    "ALTER TABLE tournament_settings ADD COLUMN IF NOT EXISTS tournament_id INTEGER REFERENCES tournaments(id)",
    "ALTER TABLE tournament_settings ADD COLUMN IF NOT EXISTS knockout_rules_json JSONB",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(120)",
    """
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email') THEN
        UPDATE users SET username = COALESCE(username, NULLIF(split_part(email, '@', 1), ''), name, 'user_' || id::text);
        UPDATE users SET username = 'admin' WHERE (email LIKE '%admin%' OR name ILIKE 'admin') AND username IS DISTINCT FROM 'admin';
        ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
      END IF;
    END $$;
    """,
    "UPDATE users SET username = COALESCE(username, 'user_' || id::text) WHERE username IS NULL",
    "ALTER TABLE users ALTER COLUMN username SET NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username)",
    """
    CREATE TABLE IF NOT EXISTS user_match_scores (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        match_id INTEGER NOT NULL REFERENCES matches(id),
        points_earned INTEGER NOT NULL DEFAULT 0,
        breakdown_json JSONB,
        updated_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT uq_user_match_score UNIQUE (user_id, match_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_user_match_scores_user_id ON user_match_scores(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_user_match_scores_match_id ON user_match_scores(match_id)",
]


async def run_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for stmt in MIGRATIONS:
            await conn.execute(text(stmt))

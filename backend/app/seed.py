import asyncio

from sqlalchemy import select

from app.auth.security import hash_password
from app.config import settings
from app.database import async_session, engine, Base
from app.db_migrate import run_migrations
from app.models import Tournament, User
from app.seeds.tournament_loader import import_tournament


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with async_session() as db:
        admin_result = await db.execute(select(User).where(User.username == settings.admin_username))
        if not admin_result.scalar_one_or_none():
            db.add(
                User(
                    username=settings.admin_username,
                    name="Admin",
                    password_hash=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )
            await db.flush()

        t_result = await db.execute(select(Tournament).limit(1))
        if not t_result.scalar_one_or_none():
            result = await import_tournament(db, "worldcup_2026", reset=False, set_active=True)
            print(f"Imported tournament: {result}")
        else:
            print("Tournament already loaded")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())

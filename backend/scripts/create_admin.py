import asyncio
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole

settings = get_settings()


async def create_or_seed_admin():
    email = settings.ADMIN_EMAIL.strip().lower()
    password = settings.ADMIN_PASSWORD

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print(f"Admin account already exists for {email}. Updating role to admin.")
            existing_admin.role = UserRole.ADMIN
            existing_admin.is_active = True
            await session.commit()
            print("Admin verified.")
            return

        admin_user = User(
            name="System Administrator",
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        print(f"Successfully seeded admin account: {email}")


if __name__ == "__main__":
    asyncio.run(create_or_seed_admin())

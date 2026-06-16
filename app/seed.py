"""
Run with:  python -m app.seed
"""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, create_tables
from app.crud.business import create_business


SEED_DATA = [
    {
        "name": "فروشگاه آنلاین نمونه",
        "type": "shop",
        "field": "فروش لوازم الکترونیکی",
        "contact": "021-12345678",
        "working_hours": "شنبه تا چهارشنبه ۹ تا ۱۸",
        "details": {
            "products": "موبایل، لپ‌تاپ، هدفون، شارژر",
            "return_policy": "۷ روز ضمانت بازگشت کالا",
        },
    },
    {
        "name": "آموزشگاه نمونه",
        "type": "education",
        "field": "آموزش برنامه‌نویسی",
        "contact": "021-87654321",
        "working_hours": "شنبه تا پنجشنبه ۸ تا ۲۰",
        "details": {
            "courses": "پایتون، جاوااسکریپت، هوش مصنوعی",
            "age_range": "۱۲ تا ۵۰ سال",
        },
    },
    {
        "name": "شرکت خدمات نمونه",
        "type": "service",
        "field": "خدمات نظافت منزل",
        "contact": "021-11223344",
        "working_hours": "همه روزه ۸ تا ۲۲",
        "details": {
            "services": "نظافت خانه، نظافت اداری، قالیشویی",
            "service_area": "تهران و کرج",
        },
    },
]


async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        for data in SEED_DATA:
            business = await create_business(db, data.copy())
            print(f"Created: {business.name}  id={business.id}")


if __name__ == "__main__":
    asyncio.run(seed())

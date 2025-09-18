import asyncio
from app.database import engine, Base
from app.models import Usuario, Analisis  # Importar los modelos

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tablas creadas exitosamente")

if __name__ == "__main__":
    asyncio.run(init_db())
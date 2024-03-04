import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')


async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS Position (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE
        );
    ''')

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS Employees (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(255) NOT NULL,
            last_name VARCHAR(255) NOT NULL,
            photo_url TEXT,
            birth_date DATE NOT NULL,
            position_id INTEGER,
            FOREIGN KEY (position_id) REFERENCES Position(id)
        );
    ''')

    print("Tables created successfully.")

    await conn.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(create_tables())











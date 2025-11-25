# database.py - PostgreSQL version
import asyncpg
import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")  # Railway provides this automatically

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    name TEXT,
    credits REAL NOT NULL DEFAULT 3.0,
    phone_number TEXT
);

CREATE TABLE IF NOT EXISTS requests (
    request_id SERIAL PRIMARY KEY,
    requester_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    hours REAL NOT NULL,
    open BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    
    accepter_id BIGINT,
    accepted_at TIMESTAMP,
    has_been_claimed BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (requester_id) REFERENCES users(telegram_id),
    FOREIGN KEY (accepter_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS claims (
    request_id INTEGER,
    accepter_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    hours REAL NOT NULL,

    FOREIGN KEY (request_id) REFERENCES requests(request_id),
    FOREIGN KEY (accepter_id) REFERENCES users(telegram_id)
);
"""

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(INIT_SQL)

async def user_exists(telegram_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT 1 FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return result is not None

async def create_request(telegram_id, title, desc, hours):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT credits FROM users WHERE telegram_id = $1",
                telegram_id
            )
            if not row:
                return False

            credits = row['credits'] - hours
            if credits < 0:
                return False

            await conn.execute(
                "INSERT INTO requests (requester_id, title, description, hours) VALUES ($1, $2, $3, $4)",
                telegram_id, title, desc, hours
            )

            await conn.execute(
                "UPDATE users SET credits = $1 WHERE telegram_id = $2",
                credits, telegram_id
            )

            return True

async def accept_request(request_id, accepter_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE requests SET open = FALSE, accepter_id = $1, accepted_at = NOW() WHERE request_id = $2 AND open = TRUE",
            accepter_id, request_id
        )

async def claim_request(request_id, claimer_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    "SELECT requester_id, accepter_id, title, hours, cancelled FROM requests WHERE request_id = $1",
                    request_id
                )
                if not row:
                    return False

                requester_id, accepter_id, title, hours, cancelled = row['requester_id'], row['accepter_id'], row['title'], row['hours'], row['cancelled']

                if cancelled:
                    return False

                if accepter_id != claimer_id:
                    return False

                accepter = await conn.fetchrow(
                    "SELECT credits FROM users WHERE telegram_id = $1",
                    accepter_id
                )
                accepter_credits = accepter['credits'] + hours

                await conn.execute(
                    "UPDATE users SET credits = $1 WHERE telegram_id = $2",
                    accepter_credits, accepter_id
                )
                await conn.execute(
                    "UPDATE requests SET has_been_claimed = TRUE WHERE request_id = $1",
                    request_id
                )
                await conn.execute(
                    "INSERT INTO claims (request_id, accepter_id, title, hours) VALUES ($1, $2, $3, $4)",
                    request_id, accepter_id, title, hours
                )

                return True
            except Exception as e:
                print(f"Claim error: {e}")
                return False

async def claim_refund(request_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT requester_id, hours FROM requests WHERE request_id = $1",
                request_id
            )
            if not row:
                return False
            
            await conn.execute(
                "UPDATE requests SET cancelled = TRUE WHERE request_id = $1",
                request_id
            )

            requester_id, hours = row['requester_id'], row['hours']
            user = await conn.fetchrow(
                "SELECT credits FROM users WHERE telegram_id = $1",
                requester_id
            )

            if not user:
                return False
            
            requester_credits = user['credits'] + hours
            await conn.execute(
                "UPDATE users SET credits = $1 WHERE telegram_id = $2",
                requester_credits, requester_id
            )
            return True

async def get_user(telegram_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return row if row else None

async def add_user(telegram_id, name, credits=3.0, phone_number=None):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (telegram_id, name, credits, phone_number) VALUES ($1, $2, $3, $4)",
                telegram_id, name, credits, phone_number
            )
    except Exception as e:
        print(f"Error adding user: {e}")

async def update_user(telegram_id, **fields):
    if not fields:
        return
    
    pool = await get_pool()
    set_clause = ", ".join(f"{key} = ${i+1}" for i, key in enumerate(fields.keys()))
    values = list(fields.values()) + [telegram_id]
    
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {set_clause} WHERE telegram_id = ${len(values)}",
            *values
        )

async def update_request(request_id, **fields):
    if not fields:
        return
    
    pool = await get_pool()
    set_clause = ", ".join(f"{key} = ${i+1}" for i, key in enumerate(fields.keys()))
    values = list(fields.values()) + [request_id]
    
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE requests SET {set_clause} WHERE request_id = ${len(values)}",
            *values
        )

async def get_db():
    """Compatibility function - returns pool connection context"""
    pool = await get_pool()
    return pool.acquire()
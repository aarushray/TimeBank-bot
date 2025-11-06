# database.py
import aiosqlite
from pathlib import Path
from datetime import datetime
import time

DB_PATH = Path("timebank.db")

INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    name TEXT,
    credits REAL NOT NULL DEFAULT 3.0,
    phone_number TEXT
);

CREATE TABLE IF NOT EXISTS requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    hours REAL NOT NULL,
    open INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled INTEGER NOT NULL DEFAULT 0,
    
    accepter_id INTEGER,
    accepted_at TEXT,
    has_been_claimed INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (requester_id) REFERENCES users(telegram_id),
    FOREIGN KEY (accepter_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS claims (
    request_id INTEGER,
    accepter_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    hours REAL NOT NULL,

    FOREIGN KEY (request_id) REFERENCES requests(request_id),
    FOREIGN KEY (accepter_id) REFERENCES users(telegram_id)
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SQL)
        await db.commit()


def get_db():
    return aiosqlite.connect(DB_PATH)

async def user_exists(telegram_id):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT 1 FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        return (await cur.fetchone()) is not None

async def create_request(telegram_id, title, desc, hours):
    async with get_db() as db:
        cur = await db.execute("SELECT credits FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            return False  # user does not exist

        credits = row[0] - hours
        if credits < 0:
            return False  # not enough credits

        await db.execute(
            "INSERT INTO requests (requester_id, title, description, hours) VALUES (?, ?, ?, ?)",
            (telegram_id, title, desc, hours)
        )

        await db.execute(
            "UPDATE users SET credits = ? WHERE telegram_id = ?",
            (credits, telegram_id)
        )

        await db.commit()
        return True

async def accept_request(request_id, accepter_id):
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")  # lock row to prevent races
        await db.execute(
            "UPDATE requests SET open = 0, accepter_id = ?, accepted_at = datetime('now') WHERE request_id = ? AND open = 1",
            (accepter_id, request_id),
        )
        await db.commit()

async def claim_request(request_id, claimer_id):
    async with get_db() as db:
        try:
            cur = await db.execute("SELECT requester_id, accepter_id, title, hours, cancelled FROM requests WHERE request_id = ?", (request_id,))
            row = await cur.fetchone()
            if not row:
                return False

            requester_id, accepter_id, title, hours, cancelled = row

            if cancelled:
                return False  # Request was cancelled

            if accepter_id != claimer_id:
                return False  # Only accepter can claim

            # Add credits to accepter
            cur = await db.execute("SELECT credits FROM users WHERE telegram_id = ?", (accepter_id,))
            accepter_credits = (await cur.fetchone())[0] + hours

            await db.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (accepter_credits, accepter_id))
            await db.execute("UPDATE requests SET has_been_claimed = 1 WHERE request_id = ?", (request_id,))
            await db.execute("INSERT INTO claims (request_id, accepter_id, title, hours) VALUES (?, ?, ?, ?)",
                            (request_id, accepter_id, title, hours))

            await db.commit()
            return True
        except Exception as e:
            print("nobody accepted")
            await db.execute("ROLLBACK")

async def claim_refund(request_id):
    async with get_db() as db:
        curr = await db.execute("SELECT requester_id, hours from requests WHERE request_id = ?", (request_id,))
        row = await curr.fetchone()
        if not row:
            return False  # No such request
        
        await db.execute("UPDATE requests SET cancelled = 1 WHERE request_id = ?", (request_id,))

        requester_id, hours = row
        curr = await db.execute("SELECT credits from users WHERE telegram_id = ?", (requester_id,))
        row = await curr.fetchone()

        if not row:
            return False  # No such user
        requester_credits = row[0]
        requester_credits += hours
        await db.execute(
            "UPDATE users SET credits = ? WHERE telegram_id = ?",
            (requester_credits, requester_id)
        )
        await db.commit()
        return True

async def get_user(telegram_id):
    async with get_db() as db:
        curr = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        rows = await curr.fetchone()
        return rows if rows else None

async def add_user(telegram_id, name, credits=3.0, phone_number=None):
    try:
        print('in db')
        await init_db()
        async with get_db() as db:
            print('got db')
            await db.execute(
                "INSERT INTO users (telegram_id, name, credits, phone_number) VALUES (?, ?, ?, ?)",
                (telegram_id, name, credits, phone_number)
            )
            print('added user')
            await db.commit()
    except Exception as e:
        print(f"Error adding user: {e}")

async def update_user(telegram_id, **fields):
    if not fields:
        return  # Nothing to update
    
    async with get_db() as db:
        # Dynamically build SET clause
        set_clause = ", ".join(f"{key} = ?" for key in fields.keys())
        values = list(fields.values()) + [telegram_id]

        await db.execute(
            f"UPDATE users SET {set_clause} WHERE telegram_id = ?",
            values
        )
        await db.commit()

async def update_request(request_id, **fields):
    if not fields:
        return  # Nothing to update
    
    async with get_db() as db:
        # Dynamically build SET clause
        set_clause = ", ".join(f"{key} = ?" for key in fields.keys())
        values = list(fields.values()) + [request_id]

        await db.execute(
            f"UPDATE requests SET {set_clause} WHERE request_id = ?",
            values
        )
        await db.commit()



# if __name__ == "__main__":
#     import asyncio

#     async def _smoke():

    
#         await init_db()
#         async with get_db() as db:
#             # add two users
#             await check_user_exists("Alice", "91234567")
#             await check_user_exists("Bob",   "90001122")
#             await check_user_exists("Charlie", "90003344")

#             # create a request for Alice
#             await create_request("Alice", "91234567", "Clinic Companion", "Need 2h for appointment", 2.0)


#             curr = await db.execute("SELECT request_id FROM requests WHERE requester_name = 'Alice'")
#             row = await curr.fetchone()

#             # accept by Bob
#             # await accept_request(row[0], "Bob", "90001122")
#             # await accept_request(db, row[0], "Charlie", "90003344")  # should be no-op

#             await claim_request(row[0]) #error

#             # read back
#             time.sleep(1)

#             # await claim_refund(db, row[0])
            

#             # try FK failure: insert accept from unknown phone -> should raise
#             try:
#                 await accept_request(row[0], "Eve", "00000000")
#                 await claim_request(row[0])
#             except Exception as e:
#                 print("FK error as expected:", type(e).__name__, str(e)[:80])

#     asyncio.run(_smoke())



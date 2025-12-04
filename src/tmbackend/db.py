from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
import os
from typing import Optional
import asyncio

# Load .env so MONGO_URI and DATABASE_NAME are available
load_dotenv()


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None
    users_collection = None
    resumes_collection = None
    tailored_resumes_collection = None


db = Database()


async def connect_to_mongo():
    """Create database connection"""
    try:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise RuntimeError("MONGO_URI is not set. Check your .env or environment variables.")

        # Optional debug:
        # print("Using MONGO_URI:", mongo_uri)

        db.client = AsyncIOMotorClient(
            mongo_uri,
            maxPoolSize=10,
            minPoolSize=1,
        )

        # Test the connection
        await db.client.admin.command("ping")

        # Set database and collections
        database_name = os.getenv("DATABASE_NAME", "resume_builder")
        db.database = db.client[database_name]
        db.users_collection = db.database.users
        db.resumes_collection = db.database.resumes
        db.tailored_resumes_collection = db.database.tailored_resumes


        # Create indexes for better performance
        await create_indexes()

        print("Connected to MongoDB")

    except ConnectionFailure as e:
        print(f"Could not connect to MongoDB: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error connecting to MongoDB: {e}")
        raise


async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        print("Disconnected from MongoDB")


async def create_indexes():
    """Create database indexes for better performance"""
    try:
        # Users collection indexes
        await db.users_collection.create_index("google_sub", unique=True)
        await db.users_collection.create_index("email")

        # Resumes collection indexes
        await db.resumes_collection.create_index(
            [("user_id", 1), ("is_deleted", 1)]
        )
        await db.resumes_collection.create_index("date_uploaded")

        print("Database indexes created")
    except Exception as e:
        print(f"Error creating indexes: {e}")


def get_database():
    """Get database instance"""
    return db

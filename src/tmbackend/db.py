from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
import os
from typing import Optional
import asyncio

class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None
    users_collection = None
    resumes_collection = None

db = Database()

async def connect_to_mongo():
    """Create database connection"""
    try:
        db.client = AsyncIOMotorClient(
            os.getenv("MONGO_URI", "mongodb://localhost:27017"),
            maxPoolSize=10,
            minPoolSize=1,
        )
        
        # Test the connection
        await db.client.admin.command('ping')
        
        # Set database and collections
        database_name = os.getenv("DATABASE_NAME", "resume_builder")
        db.database = db.client[database_name]
        db.users_collection = db.database.users
        db.resumes_collection = db.database.resumes
        
        # Create indexes for better performance
        await create_indexes()
        
        print("Connected to MongoDB")
        
    except ConnectionFailure as e:
        print(f"Could not connect to MongoDB: {e}")
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
        await db.resumes_collection.create_index([
            ("user_id", 1), 
            ("is_deleted", 1)
        ])
        await db.resumes_collection.create_index("date_uploaded")
        
        print("Database indexes created")
    except Exception as e:
        print(f"Error creating indexes: {e}")

def get_database():
    """Get database instance"""
    return db


from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb+srv://nithish03:nithish03@cluster0.zcfarfw.mongodb.net/"
client = AsyncIOMotorClient(MONGO_URL)
db = client.company_db
users_collection = db.users

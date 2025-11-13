from pymongo import MongoClient
import os
from dotenv import load_dotenv
import redis

load_dotenv()

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), db=0, decode_responses=True)

MONGO_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client["all_users"]
users = db["users"]
business_numbers=client['business_numbers']['numbers']
def check_wallet_by_number(phone_number: str) -> str:
    """Check wallet address for a number, using Redis cache."""
    cache_key = f"wallet_address:{phone_number}"
    cached_address = r.get(cache_key)
    if cached_address:
        print("From Cache")
        return f"✅ Wallet found: {cached_address}"

    record = users.find_one({"number": phone_number})
    if record and "address" in record:
        address = record["address"]
        r.setex(cache_key, 3600, address)  # Cache for 1 hour
        return f"✅ Wallet found: {address}"

    return "❌ No wallet associated with this number."


def get_business_wallet_by_number(phone_number: str) -> str:
    """Retrieve the wallet address associated with a business phone number."""
    record = business_numbers.find_one({"number": phone_number})
    if record and "address" in record:
        return f"✅ Business wallet: {record['address']}"
    return "❌ No wallet associated with this business number."

if __name__ == "__main__":
    print(get_business_wallet_by_number("+14155238886"))
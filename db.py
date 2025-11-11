from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client["all_users"]
users = db["users"]
business_numbers=client['business_numbers']['numbers']
def check_wallet_by_number(phone_number: str) -> bool:
    """Check if a wallet address is associated with a given phone number."""
    record = users.find_one({"number": phone_number})
    if record and "address" in record:
        return f"✅ Wallet found: {record['address']}"
    return "❌ No wallet associated with this number."

def get_business_wallet_by_number(phone_number: str) -> str:
    """Retrieve the wallet address associated with a business phone number."""
    record = business_numbers.find_one({"number": phone_number})
    if record and "address" in record:
        return f"✅ Business wallet: {record['address']}"
    return "❌ No wallet associated with this business number."

if __name__ == "__main__":
    print(get_business_wallet_by_number("+14155238886"))
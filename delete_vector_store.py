import shutil
import os 
# Delete specific phone number's vector store
local_path = "/tmp/+14155238886/vector_store"
if os.path.exists(local_path):
    shutil.rmtree(local_path)
    print(f"✅ Deleted local vector store: {local_path}")
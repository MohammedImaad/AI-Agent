import os
import boto3
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")

model = SentenceTransformer("all-MiniLM-L6-v2")
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=AWS_REGION
)
def ensure_vector_store_local(phone_number: str) -> str:
    """
    Ensure the vector store for this phone number exists locally.
    Downloads from S3 if not already present.
    """
    local_path = f"/tmp/{phone_number}/vector_store"
    if not os.path.exists(local_path):
        print(f"⬇️ Downloading vector store for {phone_number} from S3...")
        os.makedirs(local_path, exist_ok=True)
        prefix = f"{phone_number}/vector_store/"
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            rel_path = key[len(prefix):]
            if not rel_path:  # skip folder keys
                continue
            local_file_path = os.path.join(local_path, rel_path)
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            s3.download_file(S3_BUCKET, key, local_file_path)
        print(f"✅ Download complete: {local_path}")
    return local_path

def get_answer(query_text: str, phone_number: str):
    """
    Retrieve context from the correct vector store based on phone number.
    """
    vector_path = ensure_vector_store_local(phone_number)
    client = chromadb.PersistentClient(path=vector_path)
    collection = client.get_collection(name="pdf_documents")

    query_embedding = model.encode([query_text])
    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=3
    )
    context = results["documents"][0]
    return context


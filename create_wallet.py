import os
import base58
import keyring
import logging
import sys
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import boto3
from dotenv import load_dotenv
import base64
from db import users
import redis
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), db=0, decode_responses=True)
MAINNET_RPC_URL = "https://api.mainnet-beta.solana.com"
load_dotenv()
ARN=os.getenv("KEY_ARN")

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[%(levelname)s] %(message)s')

def create_wallet(phone_number: str):
    """Generate a new Solana wallet and store it securely in the system keyring."""
    logging.info("No key found. Generating new wallet…")
    seed = os.urandom(32)
    keypair = Keypair.from_seed(seed)
    private_key_base58 = base58.b58encode(bytes(keypair)).decode()
    encrypted_key=encrypt_private_key_with_kms(private_key_base58)

    logging.info("✅ New wallet generated and stored securely.")
    logging.info(f"Public Key: {keypair.pubkey()}")
    users.insert_one({
            "number": phone_number,
            "address": str(keypair.pubkey()),
            "private_key": encrypted_key
    })
    r.setex(f"wallet_address:{phone_number}", 3600, str(keypair.pubkey()))

    return {
        "public_key": str(keypair.pubkey()),
        "private_key_base58": private_key_base58
    }
def encrypt_private_key_with_kms(private_key_bytes: bytes, region: str = "eu-north-1") -> bytes:
    """
    Encrypt a private key using AWS KMS and return the ciphertext blob.
    
    Args:
        private_key_bytes (bytes): The private key to encrypt.
        region (str): AWS region (default: eu-north-1)
    
    Returns:
        bytes: The encrypted ciphertext blob.
    """
    ARN=os.getenv("KEY_ARN")
    kms = boto3.client("kms", region_name=region)
    encryption_context = {"purpose": "wallet_private_key"}

    response = kms.encrypt(
        KeyId=ARN,
        Plaintext=private_key_bytes,
        EncryptionContext=encryption_context,
    )
    return response["CiphertextBlob"]

def decrypt_private_key_with_kms(ciphertext_blob: bytes, region: str = "eu-north-1") -> bytes:
    """
    Decrypt an encrypted private key using AWS KMS and return the plaintext.
    
    Args:
        ciphertext_blob (bytes): The encrypted ciphertext blob (from KMS Encrypt).
        region (str): AWS region (default: eu-north-1)
    
    Returns:
        bytes: The decrypted plaintext private key.
    """
    kms = boto3.client("kms", region_name=region)
    encryption_context = {"purpose": "wallet_private_key"}

    response = kms.decrypt(
        CiphertextBlob=ciphertext_blob,
        EncryptionContext=encryption_context,
    )
    return response["Plaintext"]


    
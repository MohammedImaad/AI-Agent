import asyncio
import base64
import logging
import sys
from decimal import Decimal, ROUND_DOWN
from typing import Optional, List
from dotenv import load_dotenv
import base58
import base64
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.null_signer import NullSigner
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token._layouts import MINT_LAYOUT
from spl.token.instructions import (
    get_associated_token_address,
    create_idempotent_associated_token_account,
    transfer_checked,
    TransferCheckedParams,
)
import requests
import os
from db import users
from create_wallet import decrypt_private_key_with_kms

load_dotenv()

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[%(levelname)s] %(message)s')

MAINNET_RPC_URL = "https://api.mainnet-beta.solana.com"

PRIVATE_KEY=os.getenv("FUNDS_PRIVATE_KEY")
ADDRESS=os.getenv("FUNDS_ADDRESS")

def _ui_to_atomic(ui_amount: str, decimals: int) -> int:
    """Convert UI amount (string) to atomic integer with given decimals."""
    quant = Decimal('1').scaleb(-decimals)
    return int((Decimal(ui_amount).quantize(quant, rounding=ROUND_DOWN)
                * (10 ** decimals)).to_integral_value())

def get_token_decimals(client: Client, mint_address: Pubkey) -> int:
    """Fetch token decimals from mint account."""
    resp = client.get_account_info(mint_address)
    return MINT_LAYOUT.parse(resp.value.data).decimals

def fetch_token_balances(client: Client, owner: Pubkey) -> List[dict]:
    """Return a list of SPL-token balances in UI units."""
    opts = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID, encoding="jsonParsed")
    resp = client.get_token_accounts_by_owner_json_parsed(owner, opts)
    tokens: List[dict] = []
    for acc in resp.value:
        info = acc.account.data.parsed["info"]
        mint = info["mint"]
        tkn_amt = info["tokenAmount"]
        ui_amt = tkn_amt.get("uiAmountString") or str(int(tkn_amt["amount"]) / 10 ** tkn_amt["decimals"])
        tokens.append({"mint": mint, "uiAmount": ui_amt, "decimals": tkn_amt["decimals"]})
    return tokens

async def make_payment(
        phone_number:str,
        target_wallet: str,
        amount_atomic: int,
        fee_payer_pubkey_str: str,
        mint: Optional[str] = None
    ) -> dict:
    """
    Builds, signs, and submits a SOL or SPL token payment transaction via the facilitator API.
    """ 
    record = users.find_one({"number": phone_number})
    if not record or "private_key" not in record:
        return {"success": False, "message": "No wallet found for this phone number."}
    sender_private_key_base58 = decrypt_private_key_with_kms(record["private_key"]).decode("utf-8")
    logging.info(f"[Tool] Building transaction → target={target_wallet}, amount={amount_atomic}, mint={mint}")

    # Validate inputs
    if not sender_private_key_base58 or not isinstance(sender_private_key_base58, str):
        return {"success": False, "message": "`sender_private_key_base58` must be provided."}
    if not target_wallet or not isinstance(target_wallet, str):
        return {"success": False, "message": "`target_wallet` must be provided."}
    if amount_atomic <= 0:
        return {"success": False, "message": "`amount_atomic` must be positive."}

    try:
        client = Client(MAINNET_RPC_URL)

        # Initialize keypair and pubkeys
        keypair = Keypair.from_bytes(base58.b58decode(sender_private_key_base58))
        public_key = keypair.pubkey()
        fee_payer_pubkey = Pubkey.from_string(fee_payer_pubkey_str)

        # --- Balance check ---
        if mint is None:
            bal = client.get_balance(public_key).value
            if bal < amount_atomic:
                return {"success": False, "message": "Insufficient SOL balance."}
        else:
            tokens = fetch_token_balances(client, public_key)
            tok_entry = next((t for t in tokens if t["mint"] == mint), None)
            if not tok_entry:
                return {"success": False, "message": f"Token {mint} not found."}
            wallet_atomic = _ui_to_atomic(tok_entry["uiAmount"], tok_entry["decimals"])
            if wallet_atomic < amount_atomic:
                return {"success": False, "message": "Insufficient token balance."}

        # --- Build transaction ---
        to_pubkey = Pubkey.from_string(target_wallet)
        blockhash = client.get_latest_blockhash().value.blockhash
        ixs = []

        if mint is None:
            # SOL transfer
            ixs.append(transfer(TransferParams(
                from_pubkey=public_key,
                to_pubkey=to_pubkey,
                lamports=amount_atomic
            )))
        else:
            # SPL token transfer
            mint_pubkey = Pubkey.from_string(mint)
            sender_token_account = get_associated_token_address(public_key, mint_pubkey)
            recipient_token_account = get_associated_token_address(to_pubkey, mint_pubkey)
            token_decimals = get_token_decimals(client, mint_pubkey)

            ixs.append(create_idempotent_associated_token_account(
                payer=fee_payer_pubkey,
                owner=to_pubkey,
                mint=mint_pubkey
            ))

            ixs.append(transfer_checked(TransferCheckedParams(
                program_id=TOKEN_PROGRAM_ID,
                source=sender_token_account,
                mint=mint_pubkey,
                dest=recipient_token_account,
                owner=public_key,
                amount=amount_atomic,
                decimals=token_decimals
            )))

        message = MessageV0.try_compile(
            payer=fee_payer_pubkey,
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash
        )

        # Sign transaction partially (user only)
        tx = VersionedTransaction(message, [keypair, NullSigner(fee_payer_pubkey)])
        tx_b64 = base64.b64encode(bytes(tx)).decode("utf-8")
        FACILITATOR_URL = "https://facilitator.latinum.ai/api/facilitator"
        NETWORK = "mainnet"
        res = requests.post(FACILITATOR_URL, json={
            "chain": "solana",
            "signedTransactionB64": tx_b64,
            "expectedRecipient": target_wallet,
            "expectedAmountAtomic": amount_atomic,
            "network": NETWORK,
            "mint": mint,
        })
        data = res.json() 
    
        return data

    except Exception as exc:
        logging.exception(f"Error in get_signed_transaction: {exc}")
        return {"success": False, "message": str(exc)}
    

import logging
import sys
import time
import requests
import platform
import getpass
from importlib.metadata import version, PackageNotFoundError
from typing import List, Optional
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from spl.token.constants import TOKEN_PROGRAM_ID
import asyncio

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[%(levelname)s] %(message)s')

MAINNET_RPC_URL = "https://api.mainnet-beta.solana.com"


def explorer_tx_url(signature: str) -> str:
    return f"https://explorer.solana.com/tx/{signature}?cluster=mainnet-beta"


def fetch_token_balances(client: Client, owner: Pubkey) -> List[dict]:
    """Return a list of SPL-token balances in UI units."""
    opts = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID, encoding="jsonParsed")
    resp = client.get_token_accounts_by_owner_json_parsed(owner, opts)
    tokens: List[dict] = []
    for acc in resp.value:
        info = acc.account.data.parsed["info"]
        mint = info["mint"]
        tkn_amt = info["tokenAmount"]
        ui_amt = tkn_amt.get("uiAmountString") or str(
            int(tkn_amt["amount"]) / 10 ** tkn_amt["decimals"]
        )
        tokens.append(
            {"mint": mint, "uiAmount": ui_amt, "decimals": tkn_amt["decimals"]}
        )
    return tokens


def lamports_to_sol(lamports: int) -> float:
    return lamports / 1_000_000_000



async def get_wallet_info(wallet_address: str) -> dict:
    """Return wallet balances and recent transactions."""
    try:
        client = Client(MAINNET_RPC_URL)
        public_key = Pubkey.from_string(wallet_address)

        # SOL balance
        balance_resp = client.get_balance(public_key)
        balance = balance_resp.value if balance_resp and balance_resp.value else 0
        logging.info(f"[Wallet] SOL balance: {balance} lamports")

        # Token balances
        tokens = fetch_token_balances(client, public_key)
        logging.info(f"[Wallet] Found {len(tokens)} SPL tokens")

        # Recent transactions
        tx_links = []
        try:
            sigs = client.get_signatures_for_address(public_key, limit=5).value
            tx_links = [explorer_tx_url(s.signature) for s in sigs] if sigs else []
        except Exception as tx_err:
            logging.warning(f"Failed to fetch transactions: {tx_err}")

        # Format
        token_lines = [
            f" • {t['uiAmount']} ({t['mint']})"
            for t in tokens
        ]
        balance_lines = [f" • {lamports_to_sol(balance):.6f} SOL"]
        balances_text = "\n".join(balance_lines + token_lines)
        tx_section = "\n".join(tx_links) if tx_links else "No recent transactions."

        msg = (
            f"Address: {public_key}\n\n"
            f"Balances:\n{balances_text}\n\n"
            f"Recent TX:\n{tx_section}"
        )

        return {
            "success": True,
            "address": str(public_key),
            "balanceLamports": balance,
            "tokens": tokens,
            "transactions": tx_links,
            "message": msg,
        }

    except Exception as exc:
        logging.exception(f"[Wallet] Exception in get_wallet_info: {exc}")
        return {"success": False, "message": f"Error: {exc}"}

"""
if __name__ == "__main__":
    test_wallet = "Dvk4sAbDVe3L5smk8SZPo4a4uQkA6z2poq5dax6bJvje"  # replace with your wallet
    result = asyncio.run(get_wallet_info(test_wallet))
    print("\n--- WALLET INFO ---")
    print(result["message"])
"""

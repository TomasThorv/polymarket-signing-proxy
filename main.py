from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
import os

app = FastAPI(title="Polymarket Signing Proxy")

# Config from environment variables
PRIVATE_KEY = os.environ.get("POLY_PRIVATE_KEY")
API_KEY = os.environ.get("POLY_API_KEY")
API_SECRET = os.environ.get("POLY_API_SECRET")
API_PASSPHRASE = os.environ.get("POLY_API_PASSPHRASE")
FUNDER = os.environ.get("POLY_FUNDER_ADDRESS")
PROXY_SECRET = os.environ.get("PROXY_SECRET", "changeme")


def get_client():
    creds = type("Creds", (), {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "api_passphrase": API_PASSPHRASE,
    })()
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=PRIVATE_KEY,
        chain_id=137,
        signature_type=1,
        funder=FUNDER,
    )
    client.set_api_creds(creds)
    return client


class TradeRequest(BaseModel):
    secret: str
    token_id: str
    side: str  # "BUY" or "SELL"
    size: float  # Number of shares
    price: float  # Limit price (0.01 to 0.99)


class MarketTradeRequest(BaseModel):
    secret: str
    token_id: str
    side: str  # "BUY" or "SELL"
    amount: float  # USDC for buys, shares for sells


@app.get("/health")
def health():
    return {"status": "ok", "message": "Polymarket signing proxy is running"}


@app.post("/trade")
def place_limit_order(req: TradeRequest):
    if req.secret != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    try:
        client = get_client()
        side = BUY if req.side.upper() == "BUY" else SELL

        order_args = OrderArgs(
            token_id=req.token_id,
            price=req.price,
            size=req.size,
            side=side,
        )

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        return {
            "success": True,
            "response": response,
            "details": {
                "token_id": req.token_id,
                "side": req.side,
                "size": req.size,
                "price": req.price,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "details": {
                "token_id": req.token_id,
                "side": req.side,
                "size": req.size,
                "price": req.price,
            }
        }


@app.post("/market-trade")
def market_trade(req: MarketTradeRequest):
    if req.secret != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    try:
        client = get_client()
        side = BUY if req.side.upper() == "BUY" else SELL

        order_args = MarketOrderArgs(
            token_id=req.token_id,
            amount=req.amount,
            side=side,
        )

        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)

        return {
            "success": True,
            "response": response,
            "details": {
                "token_id": req.token_id,
                "side": req.side,
                "amount": req.amount,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "details": {
                "token_id": req.token_id,
                "side": req.side,
                "amount": req.amount,
            }
        }


class ApproveRequest(BaseModel):
    secret: str


@app.post("/approve")
def approve_allowance(req: ApproveRequest):
    """Set max USDC and conditional token allowances for Polymarket exchange contracts."""
    if req.secret != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    try:
        from web3 import Web3

        rpc = "https://rpc.ankr.com/polygon"
        w3 = Web3(Web3.HTTPProvider(rpc))
        account = w3.eth.account.from_key(PRIVATE_KEY)
        max_approval = 2**256 - 1

        # ERC20 approve ABI
        approve_abi = [{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]

        usdc = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        ctf = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
        spenders = [
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CTF Exchange
            "0xC5d563A36AE78145C45a50134d48A1215220f80a",  # Neg Risk CTF Exchange
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",  # Neg Risk Adapter
        ]

        results = []
        nonce = w3.eth.get_transaction_count(account.address)

        for token_addr in [usdc, ctf]:
            contract = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=approve_abi)
            for spender in spenders:
                tx = contract.functions.approve(
                    Web3.to_checksum_address(spender), max_approval
                ).build_transaction({
                    "from": account.address,
                    "nonce": nonce,
                    "gas": 60000,
                    "gasPrice": w3.to_wei(50, "gwei"),
                    "chainId": 137,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                results.append({"token": token_addr, "spender": spender, "tx": tx_hash.hex()})
                nonce += 1

        return {"success": True, "approvals": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/balance")
def get_balance():
    try:
        import httpx
        resp = httpx.get(f"https://data-api.polymarket.com/value?user={FUNDER}")
        return {"balance": resp.json()}
    except Exception as e:
        return {"error": str(e)}

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, LimitOrderArgs
import os
import json

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
        signature_type=1,  # POLY_PROXY for Magic wallet
        funder=FUNDER,
    )
    client.set_api_creds(creds)
    return client


class TradeRequest(BaseModel):
    secret: str  # Simple auth to prevent unauthorized access
    token_id: str  # The CLOB token ID for Yes or No outcome
    side: str  # "BUY" or "SELL"
    size: float  # Amount in USDC
    price: float  # Limit price (0.01 to 0.99)


class MarketBuyRequest(BaseModel):
    secret: str
    token_id: str
    amount: float  # USDC amount to spend


class MarketSellRequest(BaseModel):
    secret: str
    token_id: str
    amount: float  # Number of shares to sell


@app.get("/health")
def health():
    return {"status": "ok", "message": "Polymarket signing proxy is running"}


@app.post("/trade")
def place_limit_order(req: TradeRequest):
    if req.secret != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    try:
        client = get_client()
        order_args = LimitOrderArgs(
            token_id=req.token_id,
            price=req.price,
            size=req.size,
            side=req.side,
        )

        if req.side.upper() == "BUY":
            signed_order = client.create_and_post_order(order_args)
        else:
            signed_order = client.create_and_post_order(order_args)

        return {
            "success": True,
            "order": str(signed_order),
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


@app.post("/market-buy")
def market_buy(req: MarketBuyRequest):
    if req.secret != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    try:
        client = get_client()
        order_args = MarketOrderArgs(
            token_id=req.token_id,
            amount=req.amount,
        )
        result = client.create_market_order(order_args)
        return {"success": True, "order": str(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/balance")
def get_balance():
    """Get USDC balance (no auth needed - read only)"""
    try:
        client = get_client()
        # Use the data API for balance
        import httpx
        resp = httpx.get(f"https://data-api.polymarket.com/value?user={FUNDER}")
        return {"balance": resp.json()}
    except Exception as e:
        return {"error": str(e)}

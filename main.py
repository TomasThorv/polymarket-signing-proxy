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


@app.get("/balance")
def get_balance():
    try:
        import httpx
        resp = httpx.get(f"https://data-api.polymarket.com/value?user={FUNDER}")
        return {"balance": resp.json()}
    except Exception as e:
        return {"error": str(e)}

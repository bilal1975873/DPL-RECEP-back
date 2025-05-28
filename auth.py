from fastapi import APIRouter, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import requests
import time
import json
from typing import Optional
import msal
from auth_utils import (
    save_tokens, load_tokens, clear_tokens, is_token_expired,
    refresh_access_token, get_valid_tokens, log
)

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
SCOPE = "offline_access User.Read Chat.ReadWrite"
MSAL_CACHE_FILE = "msal_cache.json"

router = APIRouter()

# MSAL setup
def build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
        token_cache=cache,
    )

def get_token_cache():
    cache = msal.SerializableTokenCache()
    if os.path.exists(MSAL_CACHE_FILE):
        cache.deserialize(open(MSAL_CACHE_FILE, "r").read())
    return cache

def save_token_cache(cache):
    if cache.has_state_changed:
        with open(MSAL_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

@router.get("/login")
def login():
    log("Login started")
    auth_url = (
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize?"
        f"client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}"
        f"&response_mode=query&scope={SCOPE.replace(' ', '%20')}"
    )
    return RedirectResponse(auth_url)

@router.get("/auth/callback")
def auth_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    if error:
        log(f"Auth error: {error}")
        return JSONResponse({"error": error}, status_code=400)
    if not code:
        return JSONResponse({"error": "No code provided"}, status_code=400)
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "client_secret": CLIENT_SECRET,
    }
    resp = requests.post(token_url, data=data)
    if resp.status_code != 200:
        log(f"Token exchange failed: {resp.text}")
        return JSONResponse({"error": "Token exchange failed"}, status_code=400)
    tokens = resp.json()
    tokens["expiration_time"] = time.time() + tokens["expires_in"] - 60
    save_tokens(tokens)
    log("Access token acquired")
    return JSONResponse({"message": "Authentication successful. You can now use /send-message."})

@router.get("/logout")
def logout():
    clear_tokens()
    return {"message": "Logged out. Please /login again."}

@router.get("/ngrok-help")
def ngrok_help():
    return {
        "ngrok": "To expose your local FastAPI server, download ngrok from https://ngrok.com/download, then run: ngrok http 8000. Use the https URL it gives as your redirect_uri in Azure and .env."
    }

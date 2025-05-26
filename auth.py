from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.config import Config
from authlib.integrations.starlette_client import OAuth
from datetime import datetime, timedelta
import os
from jose import JWTError, jwt

# Load environment variables
config = Config(".env")

# OAuth2 configuration
oauth = OAuth()
oauth.register(
    name='azure',
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    server_metadata_url=f'https://login.microsoftonline.com/{os.getenv("TENANT_ID")}/v2.0/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'https://graph.microsoft.com/.default offline_access openid profile email User.Read Chat.ReadWrite Chat.Create Calendars.ReadWrite'
    }
)

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Create router
router = APIRouter()

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.get("/login")
async def login(request: Request):
    """Initiate the OAuth2 login flow"""
    redirect_uri = "https://dpl-recep-back-production.up.railway.app/auth/callback"
    return await oauth.azure.authorize_redirect(request, redirect_uri)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    """Handle the OAuth2 callback"""
    try:
        token = await oauth.azure.authorize_access_token(request)
        user = await oauth.azure.parse_id_token(request, token)
        
        # Store tokens in session
        request.session['user'] = dict(user)
        request.session['access_token'] = token['access_token']
        
        # Create JWT for frontend
        access_token = create_access_token(
            data={"sub": user["email"]},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        # Redirect to frontend with token
        frontend_url = "https://front-recep-dpl.vercel.app"
        return RedirectResponse(f"{frontend_url}?token={access_token}")
        
    except Exception as e:
        print(f"Auth callback error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/check-auth")
async def check_auth(request: Request):
    """Check if user is authenticated"""
    if 'user' not in request.session:
        return {"isAuthenticated": False}
    return {
        "isAuthenticated": True,
        "user": request.session['user']
    }

@router.get("/logout")
async def logout(request: Request):
    """Clear session data"""
    request.session.pop('user', None)
    request.session.pop('access_token', None)
    return {"message": "Successfully logged out"}

import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

import asyncio
from ai_integration import AIReceptionist
from flows import (guest_flow, SUPPLIERS, vendor_flow, validate_cnic, validate_phone, validate_name, validate_email,
                  validate_group_size, get_error_message)
from prompts import STEP_PROMPTS

# --- FastAPI & MongoDB Integration ---
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from jose import JWTError, jwt
from client_config import ClientConfig

# Load environment variables
load_dotenv()

# Get Azure AD credentials
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
    raise ValueError("Missing required Azure AD environment variables (CLIENT_ID, CLIENT_SECRET, TENANT_ID)")

# OAuth2 configuration with delegated permissions
auth_config = {
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'auth_uri': f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize',
    'token_uri': f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token',
    'scope': [
        'openid',
        'profile',
        'email',
        'Chat.ReadWrite',
        'ChatMessage.Send',
        'User.Read.All',
        'Calendars.ReadWrite'
    ],
    'redirect_uri': 'https://dpl-recep-back-production.up.railway.app/auth/callback',
}

oauth = OAuth()
oauth.register(
    name='azure',
    server_metadata_url=f'https://login.microsoftonline.com/{TENANT_ID}/v2.0/.well-known/openid-configuration',
    client_id=auth_config['client_id'],
    client_secret=auth_config['client_secret'],
    client_kwargs={'scope': ' '.join(auth_config['scope'])}
)

# JWT Settings
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Initialize FastAPI app with lifespan context
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize MongoDB connection
    retries = 3
    while retries > 0:
        try:
            await client.admin.command('ping')
            print("MongoDB connected to Atlas successfully!")
            break
        except Exception as e:
            retries -= 1
            if retries > 0:
                print(f"Failed to connect to MongoDB Atlas: {e}. Retrying... ({retries} attempts left)")
                await asyncio.sleep(2)  # Wait 2 seconds before retrying
            else:
                print(f"Failed to connect to MongoDB Atlas after multiple attempts: {e}")
                raise
    
    yield  # Application runs here
    
    # Shutdown: Close MongoDB connection
    client.close()
    print("MongoDB connection closed.")

app = FastAPI(lifespan=lifespan)

# Add CORS middleware with proper configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:3000",
        "https://front-recep-dpl.vercel.app",
        "https://dpl-recep-back-production.up.railway.app"
    ],
    allow_origin_regex=r"https://.*\.vercel\.app$",  # Allow all Vercel app domains
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type", 
        "Authorization", 
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Methods",
        "Access-Control-Allow-Headers"
    ],
    expose_headers=["*"],
    max_age=3600
)

# Load environment variables
load_dotenv()

# MongoDB Atlas setup
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

# Initialize MongoDB client
client = AsyncIOMotorClient(MONGODB_URI)
db = client.get_default_database()
visitors_collection = db["visitors"]

# Add OAuth2 and JWT configuration
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"https://login.microsoftonline.com/{os.getenv('TENANT_ID')}/oauth2/v2.0/authorize",
    tokenUrl=f"https://login.microsoftonline.com/{os.getenv('TENANT_ID')}/oauth2/v2.0/token"
)

# JWT configuration 
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Session middleware configuration
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=3600,
    session_cookie="dpl_session",
    https_only=False,  # Allow HTTP for development
    same_site="lax"    # Less strict same-site policy
)

# Authentication models
class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class TokenData(BaseModel):
    username: Optional[str] = None

# Authentication utility functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    return token_data

# Authentication routes
@app.get("/auth/login")
async def login(request: Request):
    """Login endpoint that redirects to Microsoft login"""
    return await oauth.azure.authorize_redirect(
        request, 
        auth_config['redirect_uri']
    )

@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Callback endpoint that handles the OAuth response"""
    try:
        # Get token
        token = await oauth.azure.authorize_access_token(request)
        
        # Create new client config
        client_config = ClientConfig(TENANT_ID, CLIENT_ID, CLIENT_SECRET)
        
        # Store token in session
        request.session['access_token'] = token['access_token']
        request.session['id_token'] = token.get('id_token')
        
        # Redirect to frontend
        return RedirectResponse(url="https://front-recep-dpl.vercel.app/dashboard")
        
    except Exception as e:
        print(f"Error in auth callback: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    request.session.pop('access_token', None)
    return {"message": "Successfully logged out"}

@app.get("/protected")
async def protected_route(current_user: TokenData = Depends(get_current_user)):
    return {"message": "This is a protected route", "user": current_user.username}

# Pydantic Visitor model
class Visitor(BaseModel):
    type: Literal['guest', 'vendor', 'prescheduled']
    full_name: str
    cnic: Optional[str] = None
    phone: str
    email: Optional[str] = None
    host: str
    purpose: str
    entry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: Optional[datetime] = None
    is_group_visit: bool = False
    group_id: Optional[str] = None
    total_members: int = 1
    group_members: list = []
    scheduled_time: Optional[datetime] = None

# MongoDB error handler
async def handle_db_operation(operation):
    try:
        return await operation
    except Exception as e:
        print(f"MongoDB operation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database operation failed: {str(e)}"
        )

@app.post("/visitors/", response_model=Visitor)
async def create_visitor(visitor: Visitor):
    data = visitor.dict()
    result = await handle_db_operation(visitors_collection.insert_one(data))
    if not result.acknowledged:
        raise HTTPException(status_code=500, detail="Failed to insert visitor.")
    data["_id"] = str(result.inserted_id)
    return visitor

@app.get("/visitors/", response_model=list[Visitor])
async def list_visitors():
    visitors = []
    cursor = visitors_collection.find()
    async for visitor in cursor:
        visitor["_id"] = str(visitor["_id"])
        visitors.append(visitor)
    return visitors

@app.get("/visitors/{cnic}", response_model=Visitor)
async def get_visitor(cnic: str):
    visitor = await handle_db_operation(visitors_collection.find_one({"cnic": cnic}))
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    visitor["_id"] = str(visitor["_id"])
    return Visitor(**visitor)

@app.put("/visitors/{cnic}", response_model=Visitor)
async def update_visitor(cnic: str, update: Visitor):
    result = await handle_db_operation(
        visitors_collection.update_one({"cnic": cnic}, {"$set": update.dict()})
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    return update

@app.delete("/visitors/{cnic}")
async def delete_visitor(cnic: str):
    result = await handle_db_operation(visitors_collection.delete_one({"cnic": cnic}))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    return {"detail": "Visitor deleted."}

async def insert_visitor_to_db(visitor_type, full_name, cnic, phone, host, purpose, is_group_visit=False, group_members=None, total_members=1, email=None, scheduled_time=None):
    entry_time = datetime.now(timezone.utc)
    group_id = None
    
    if is_group_visit:
        group_id = str(datetime.now(timezone.utc).timestamp())

    visitor_doc = {
        "type": visitor_type,
        "full_name": full_name,
        "cnic": cnic,
        "phone": phone,
        "email": email,  # Added email field
        "host": host,
        "purpose": purpose,
        "entry_time": entry_time,
        "exit_time": None,
        "is_group_visit": is_group_visit,
        "group_id": group_id,
        "total_members": total_members,
        "group_members": group_members or [],
        "scheduled_time": scheduled_time  # Added scheduled_time field
    }
    await visitors_collection.insert_one(visitor_doc)

class VisitorInfo:
    def __init__(self):
        self.visitor_type = None
        self.visitor_name = None
        self.visitor_cnic = None
        self.visitor_phone = None
        self.host_requested = None
        self.host_confirmed = None
        self.host_email = None
        self.purpose = None
        self.verification_status = None
        self.supplier = None  # For vendor flow
        self.group_id = None  # For group visits
        self.is_group_visit = False
        self.group_members = []  # List to store additional visitors
        self.total_members = 1  # Default to 1, will be updated for groups
        self.visitor_email = None  # For pre-scheduled visits
        self.scheduled_meeting = None  # For storing found meeting details
        
    def to_dict(self):
        return {
            "visitor_type": self.visitor_type,
            "visitor_name": self.visitor_name,
            "visitor_cnic": self.visitor_cnic,
            "visitor_phone": self.visitor_phone,
            "host_requested": self.host_requested,
            "host_confirmed": self.host_confirmed,
            "host_email": self.host_email,
            "purpose": self.purpose,
            "verification_status": self.verification_status,
            "supplier": self.supplier,
            "group_id": self.group_id,
            "is_group_visit": self.is_group_visit,
            "total_members": self.total_members,
            "group_members": self.group_members,
            "visitor_email": self.visitor_email,
            "scheduled_meeting": self.scheduled_meeting
        }
    
    def summary(self):
        lines = ["=== Visitor Information Summary ==="]
        if self.visitor_name:
            lines.append(f"Name: {self.visitor_name}")
        if self.visitor_cnic:
            lines.append(f"CNIC: {self.visitor_cnic}")
        if self.visitor_phone:
            lines.append(f"Phone: {self.visitor_phone}")
        if self.host_confirmed:
            lines.append(f"Host: {self.host_confirmed}")
        if self.purpose:
            lines.append(f"Purpose: {self.purpose}")
        return "\n".join(lines)

class DPLReceptionist:
    def __init__(self):
        self.visitor_info = VisitorInfo()
        self.ai = AIReceptionist()
        self.current_step = "visitor_type"
        self.employee_selection_mode = False
        self.employee_matches = []
        
    def reset(self):
        self.__init__()
        
    async def process_input(self, user_input: str) -> str:
        # Handle visitor type selection (only at the very start)
        if self.current_step == "visitor_type":
            user_input = user_input.lower().strip()
            context = {"current_step": "visitor_type", **self.visitor_info.to_dict()}
            
            # Handle invalid input before trying AI response
            if not user_input:
                return "Please select: 1 for Guest, 2 for Vendor, 3 for Pre-scheduled Meeting"
            
            # First try AI response for visitor type
            ai_response = await self.get_ai_response(user_input, context)
            
            if user_input in ["1", "guest"]:
                self.visitor_info.visitor_type = "guest"
                self.current_step = "name"
            elif user_input in ["2", "vendor"]:
                self.visitor_info.visitor_type = "vendor"
                self.current_step = "supplier"
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                ai_msg = await self.get_ai_response(user_input, context)
                return f"{ai_msg or STEP_PROMPTS['vendor_supplier']}\n\n{supplier_list}"
            elif user_input in ["3", "prescheduled", "scheduled"]:
                self.visitor_info.visitor_type = "prescheduled"
                self.current_step = "scheduled_name"
            else:
                # Return standard error message for invalid input
                return get_error_message("visitor_type")
                
            # Update context with new step
            context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
            
            if self.current_step == "supplier":
                # For supplier step, combine AI response with supplier list
                supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                ai_msg = await self.get_ai_response(user_input, context)
                return f"{ai_msg}\n\n{supplier_list}"
                
            return await self.get_ai_response(user_input, context)

        # Handle pre-scheduled meeting flow
        if self.visitor_info.visitor_type == "prescheduled":
            if self.current_step == "scheduled_name":
                if not user_input.strip():
                    return get_error_message("empty")
                if not validate_name(user_input.strip()):
                    return get_error_message("name")
                self.visitor_info.visitor_name = user_input.strip()
                self.current_step = "scheduled_cnic"
                return "Please provide your CNIC number in the format: 12345-1234567-1"
            elif self.current_step == "scheduled_cnic":
                if not validate_cnic(user_input.strip()):
                    return get_error_message("cnic")
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "scheduled_phone"
                return "Please provide your contact number."
            elif self.current_step == "scheduled_phone":
                if not validate_phone(user_input.strip()):
                    return get_error_message("phone")
                self.visitor_info.visitor_phone = user_input.strip()
                self.current_step = "scheduled_email"
                return "Please enter your email address:"
            elif self.current_step == "scheduled_email":
                if not validate_email(user_input.strip()):
                    return get_error_message("email")
                self.visitor_info.visitor_email = user_input.strip()
                self.current_step = "scheduled_host"
                return "Please enter the name of the person you're scheduled to meet with:"
            elif self.current_step == "scheduled_host":
                return await self.handle_scheduled_host_step(user_input)
            elif self.current_step == "scheduled_confirm":
                # Check if user chose to proceed as guest
                if user_input == "1":
                    # Convert to guest flow while keeping the visitor info
                    self.visitor_info.visitor_type = "guest"
                    self.current_step = "purpose"
                    return "What is the purpose of your visit?"
                elif user_input == "2":
                    self.current_step = "scheduled_host"
                    return "Please enter your host's name."
                elif user_input.lower() == "confirm":
                    self.current_step = "complete"
                    if self.visitor_info.scheduled_meeting:  # If there was a scheduled meeting
                        meeting = self.visitor_info.scheduled_meeting
                        # Insert into DB
                        scheduled_time = None
                        start_time = meeting.get('original_event', {}).get('start', {}).get('dateTime')
                        if start_time:
                            scheduled_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        
                        await insert_visitor_to_db(
                            visitor_type="prescheduled",
                            full_name=self.visitor_info.visitor_name,
                            cnic=self.visitor_info.visitor_cnic,
                            phone=self.visitor_info.visitor_phone,
                            host=self.visitor_info.host_confirmed,
                            purpose=meeting['purpose'],
                            is_group_visit=False,
                            email=self.visitor_info.visitor_email,
                            scheduled_time=scheduled_time
                        )
                        # Notify host via Teams
                        try:
                            access_token = self.ai.get_system_account_token()
                            host_user_id = self.ai.get_user_id(self.visitor_info.host_email, access_token)
                            system_user_id = self.ai.get_user_id(self.ai._system_account_email, access_token)
                            chat_id = self.ai.create_or_get_chat(host_user_id, system_user_id, access_token)
                            message = f"""Your scheduled visitor has arrived:
Name: {self.visitor_info.visitor_name}
Phone: {self.visitor_info.visitor_phone}
Email: {self.visitor_info.visitor_email}
Scheduled Time: {meeting['scheduled_time']}
Purpose: {meeting['purpose']}"""
                            await self.ai.send_message_to_host(chat_id, access_token, message)
                            print(f"Teams notification sent to {self.visitor_info.host_confirmed}")
                        except Exception as e:
                            print(f"Error in Teams notification process: {e}")
                        return f"Welcome! Please take a seat. {self.visitor_info.host_confirmed} has been notified of your arrival."
                    else:
                        # Handle guest flow confirmation
                        await insert_visitor_to_db(
                            visitor_type="guest",
                            full_name=self.visitor_info.visitor_name,
                            cnic=self.visitor_info.visitor_cnic,
                            phone=self.visitor_info.visitor_phone,
                            host=self.visitor_info.host_confirmed,
                            purpose=self.visitor_info.purpose,
                            email=self.visitor_info.visitor_email
                        )
                        # Try to notify the host via Teams
                        try:
                            await self.ai.schedule_meeting(
                                self.visitor_info.host_email,
                                self.visitor_info.visitor_name,
                                self.visitor_info.purpose
                            )
                        except Exception as e:
                            print(f"Error scheduling meeting: {e}")
                        return "Your registration is complete."
                elif user_input.lower() == "back":
                    self.current_step = "scheduled_host"
                    return "Please enter the name of the person you're scheduled to meet with:"
                else:
                    return "Please type 'confirm' to proceed or 'back' to re-enter the host name."

        # Guest flow (strict, only hardcoded prompts, strict step order)
        if self.visitor_info.visitor_type == "guest":
            steps = guest_flow["steps"]
            step_idx = steps.index(self.current_step) if self.current_step in steps else 0
            if self.current_step == "name":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                if not user_input.strip():
                    return get_error_message("empty")
                if not validate_name(user_input.strip()):
                    return get_error_message("name")
                self.visitor_info.visitor_name = user_input.strip()
                self.current_step = "cnic"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or "Please provide your CNIC number in the format: 12345-1234567-1."
            elif self.current_step == "cnic":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                if not validate_cnic(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "invalid_cnic"}) or "Please provide a valid CNIC number in the format: 12345-1234567-1."
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "phone"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or "Please enter your phone number."
            elif self.current_step == "cnic":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                if not validate_cnic(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "invalid_cnic"}) or "Please provide a valid CNIC number in the format: 12345-1234567-1."
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "phone"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or "Please enter your phone number."
            elif self.current_step == "phone":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                if not validate_phone(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "invalid_phone"}) or "Please enter a valid phone number."
                self.visitor_info.visitor_phone = user_input.strip()
                
                self.current_step = "host"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or "Who are you visiting?"

            elif self.current_step == "host":
                if self.employee_selection_mode:
                    # Handle employee selection by either number or name
                    if user_input.lower() == "none of these" or user_input.lower() == "none of these / enter a different name":
                        # User wants to search for a different name
                        self.employee_selection_mode = False
                        self.employee_matches = []
                        return "Please enter a different name."
                    
                    # Try to find by number first
                    if user_input.isdigit():
                        index = int(user_input) - 1
                        if 0 <= index < len(self.employee_matches):
                            selected_employee = self.employee_matches[index]
                        else:
                            selected_employee = None
                    else:
                        # Try to find the selected employee by matching the display name
                        selected_employee = next(
                            (emp for emp in self.employee_matches 
                             if emp["displayName"].lower() == user_input.lower() or
                             user_input.lower() in emp["displayName"].lower()),
                            None
                        )
                    
                    if selected_employee:
                        self.visitor_info.host_confirmed = selected_employee["displayName"]
                        self.visitor_info.host_email = selected_employee["email"]
                        # Reset selection mode
                        self.employee_selection_mode = False
                        self.employee_matches = []
                        self.current_step = "purpose"
                        return "Please provide the purpose of your visit."
                    else:
                        # Invalid selection, show options again
                        options = "Please select one of these names:\n"
                        for emp in self.employee_matches:
                            dept = emp.get("department", "Unknown Department")
                            options += f"{emp['displayName']} ({dept})\n"
                        options += "None of these / Enter a different name"
                        return options
                else:
                    # Search for employee by name
                    employee = await self.ai.search_employee(user_input)
                    if isinstance(employee, dict):
                        # Even for single match, show it to user for confirmation
                        self.employee_selection_mode = True
                        self.employee_matches = [employee]
                        options = "I found the following match. Please select:\n"
                        dept = employee.get("department", "Unknown Department")
                        options += f"{employee['displayName']} ({dept})\n"
                        options += "None of these / Enter a different name"
                        return options
                    elif isinstance(employee, list):
                        self.employee_selection_mode = True
                        self.employee_matches = employee
                        options = "I found multiple potential matches. Please select one:\n"
                        for emp in employee:
                            dept = emp.get("department", "Unknown Department")
                            options += f"{emp['displayName']} ({dept})\n"
                        options += "None of these / Enter a different name"
                        return options
                    else:
                        return "No matches found. Please enter a different name."
            elif self.current_step == "purpose":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                if not user_input.strip():
                    return await self.get_ai_response(user_input, {**context, "validation_error": "empty_purpose"}) or "Please provide the purpose of your visit."
                self.visitor_info.purpose = user_input.strip()
                self.current_step = "confirm"
                context["current_step"] = self.current_step
                # Always show summary for confirmation
                summary = f"Name: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                if self.visitor_info.host_confirmed:
                    summary += f"\nHost: {self.visitor_info.host_confirmed}"
                if self.visitor_info.purpose:
                    summary += f"\nPurpose: {self.visitor_info.purpose}"
                return f"Please review your information and type 'confirm' to proceed or 'edit' to make changes.\n{summary}"
            elif self.current_step == "confirm":
                if user_input.lower() == "confirm":
                    self.current_step = "complete"
                    await insert_visitor_to_db(
                        visitor_type=self.visitor_info.visitor_type or "guest",
                        full_name=self.visitor_info.visitor_name or "",
                        cnic=self.visitor_info.visitor_cnic or "",
                        phone=self.visitor_info.visitor_phone or "",
                        host=self.visitor_info.host_confirmed or "",
                        purpose=self.visitor_info.purpose or "",
                        is_group_visit=self.visitor_info.is_group_visit,
                        group_members=self.visitor_info.group_members,
                        total_members=self.visitor_info.total_members
                    )
                    # Schedule meeting and notify host
                    try:
                        if self.ai.graph_client is not None:
                            await self.ai.schedule_meeting(
                                self.visitor_info.host_email,
                                self.visitor_info.visitor_name,
                                self.visitor_info.purpose
                            )
                    except Exception as e:
                        print(f"Error scheduling meeting: {e}")
                    return "Your registration is complete."
                elif user_input.lower() == "edit":
                    self.current_step = "name"
                    return "Please enter your name."
                else:
                    # Show summary for confirmation again
                    summary = f"Name: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                    if self.visitor_info.is_group_visit:
                        summary += f"\nGroup size: {self.visitor_info.total_members}"
                        for idx, member in enumerate(self.visitor_info.group_members, 2):
                            summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                    if self.visitor_info.host_confirmed:
                        summary += f"\nHost: {self.visitor_info.host_confirmed}"
                    if self.visitor_info.purpose:
                        summary += f"\nPurpose: {self.visitor_info.purpose}"
                    return f"Please review your information and type 'confirm' to proceed or 'edit' to make changes.\n{summary}"
            elif self.current_step == "complete":
                return "Your registration is complete."

        # Vendor flow (strict, only hardcoded prompts, strict step order)
        if self.visitor_info.visitor_type == "vendor":
            if self.current_step == "supplier":
                context = {
                    "current_step": self.current_step,
                    **self.visitor_info.to_dict()
                }
                supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                if user_input.isdigit() and 1 <= int(user_input) <= len(SUPPLIERS):
                    selected = SUPPLIERS[int(user_input) - 1]
                    if selected == "Other":
                        self.current_step = "supplier_other"
                        context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                        return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_supplier_other"]
                    else:
                        self.visitor_info.supplier = selected
                        self.current_step = "vendor_name"
                        context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                        return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_name"]
                elif user_input.strip() in SUPPLIERS:
                    if user_input.strip() == "Other":
                        self.current_step = "supplier_other"
                        context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                        return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_supplier_other"]
                    else:
                        self.visitor_info.supplier = user_input.strip()
                        self.current_step = "vendor_name"
                        context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                        return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_name"]
                else:
                    ai_msg = await self.get_ai_response(user_input, {**context, "validation_error": "invalid_supplier"})
                    return f"{ai_msg or STEP_PROMPTS['vendor_supplier']}\n{supplier_list}"
            elif self.current_step == "supplier_other":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                if not user_input.strip():
                    return await self.get_ai_response(user_input, {**context, "validation_error": "empty"}) or get_error_message("empty")
                self.visitor_info.supplier = user_input.strip()
                self.current_step = "vendor_name"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_name"]
            elif self.current_step == "vendor_name":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                if not user_input.strip():
                    return await self.get_ai_response(user_input, {**context, "validation_error": "empty"}) or get_error_message("empty")
                if not validate_name(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "name"}) or get_error_message("name")
                self.visitor_info.visitor_name = user_input.strip()
                self.current_step = "vendor_group_size"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_group_size"]
                
            elif self.current_step == "vendor_group_size":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                try:
                    group_size = int(user_input.strip())
                    if group_size < 1:
                        return await self.get_ai_response(user_input, {**context, "validation_error": "size_too_small"}) or get_error_message("group_size")
                    if group_size > 10:
                        return await self.get_ai_response(user_input, {**context, "validation_error": "size_too_large"}) or "Maximum group size is 10 people. Please enter a smaller number."
                    self.visitor_info.total_members = group_size
                    self.visitor_info.is_group_visit = group_size > 1
                    if group_size > 1:
                        self.visitor_info.group_id = str(datetime.now(timezone.utc).timestamp())
                    self.current_step = "vendor_cnic"
                    context["current_step"] = self.current_step
                    return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_cnic"]
                except ValueError:
                    return await self.get_ai_response(user_input, {**context, "validation_error": "invalid_number"}) or get_error_message("group_size")
            elif self.current_step == "vendor_cnic":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                if not validate_cnic(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "cnic"}) or get_error_message("cnic")
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "vendor_phone"
                context["current_step"] = self.current_step
                return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_phone"]
                
            elif self.current_step == "vendor_phone":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                if not validate_phone(user_input.strip()):
                    return await self.get_ai_response(user_input, {**context, "validation_error": "phone"}) or get_error_message("phone")
                self.visitor_info.visitor_phone = user_input.strip()
                
                # If group visit, start collecting member info
                if self.visitor_info.is_group_visit and len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                    next_member = len(self.visitor_info.group_members) + 2
                    self.current_step = f"vendor_member_{next_member}_name"
                    context["current_step"] = self.current_step
                    context["next_member"] = next_member
                    return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_member_name"].replace("{number}", str(next_member))
                
                # Otherwise move to confirmation
                self.current_step = "vendor_confirm"
                context["current_step"] = self.current_step
                ai_msg = await self.get_ai_response(user_input, context)
                summary = f"Supplier: {self.visitor_info.supplier}\nName: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                if self.visitor_info.is_group_visit:
                    summary += f"\nGroup size: {self.visitor_info.total_members}"
                    for idx, member in enumerate(self.visitor_info.group_members, 2):
                        summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                return f"{ai_msg or STEP_PROMPTS['vendor_confirm']}\n{summary}"
            # Group member collection for vendor
            elif self.current_step.startswith("vendor_member_"):
                parts = self.current_step.split("_")
                member_num = int(parts[2])
                substep = parts[3]
                context = {
                    "current_step": self.current_step, 
                    "member_number": member_num,
                    **self.visitor_info.to_dict()
                }
                
                if substep == "name":
                    if not validate_name(user_input.strip()):
                        return await self.get_ai_response(user_input, {**context, "validation_error": "name"}) or get_error_message("name")
                    self.visitor_info.group_members.append({"name": user_input.strip()})
                    self.current_step = f"vendor_member_{member_num}_cnic"
                    context["current_step"] = self.current_step 
                    return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_member_cnic"].replace("{number}", str(member_num))
                elif substep == "cnic":
                    if not validate_cnic(user_input.strip()):
                        return await self.get_ai_response(user_input, {**context, "validation_error": "cnic"}) or get_error_message("cnic")
                    self.visitor_info.group_members[member_num-2]["cnic"] = user_input.strip()
                    self.current_step = f"vendor_member_{member_num}_phone"
                    context["current_step"] = self.current_step
                    return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_member_phone"].replace("{number}", str(member_num))
                elif substep == "phone":
                    if not validate_phone(user_input.strip()):
                        return await self.get_ai_response(user_input, {**context, "validation_error": "phone"}) or get_error_message("phone")
                    self.visitor_info.group_members[member_num-2]["phone"] = user_input.strip()
                    if len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                        next_member = len(self.visitor_info.group_members) + 2
                        self.current_step = f"vendor_member_{next_member}_name"
                        context["current_step"] = self.current_step
                        return await self.get_ai_response(user_input, context) or STEP_PROMPTS["vendor_member_name"].replace("{number}", str(next_member))
                    else:
                        self.current_step = "vendor_confirm" 
                        context["current_step"] = self.current_step
                        summary = f"Supplier: {self.visitor_info.supplier}\nName: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                        if self.visitor_info.is_group_visit:
                            summary += f"\nGroup size: {self.visitor_info.total_members}"
                            for idx, member in enumerate(self.visitor_info.group_members, 2):
                                summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                        ai_msg = await self.get_ai_response(user_input, context)
                        return f"{ai_msg or STEP_PROMPTS['vendor_confirm']}\n{summary}"
            elif self.current_step == "vendor_confirm":
                context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
                if user_input.lower() in ["yes", "confirm"]:
                    self.current_step = "complete"
                    context["current_step"] = self.current_step
                    
                    # Save to database
                    await insert_visitor_to_db(
                        visitor_type="vendor",
                        full_name=self.visitor_info.visitor_name or "",
                        cnic=self.visitor_info.visitor_cnic or "",
                        phone=self.visitor_info.visitor_phone or "",
                        host="Admin",
                        purpose=f"Vendor visit - {self.visitor_info.supplier}",
                        is_group_visit=self.visitor_info.is_group_visit,
                        group_members=self.visitor_info.group_members,
                        total_members=self.visitor_info.total_members
                    )
                    
                    # Try to notify admin
                    try:
                        if self.ai.graph_client is not None:
                            access_token = self.ai.get_system_account_token()
                            system_user_id = self.ai.get_user_id("saadsaad@dpl660.onmicrosoft.com", access_token)
                            admin_user_id = self.ai.get_user_id("admin_IT@dpl660.onmicrosoft.com", access_token)
                            chat_id = self.ai.create_or_get_chat(admin_user_id, system_user_id, access_token)
                            message = f"A vendor has arrived at reception:\nName: {self.visitor_info.visitor_name}\nSupplier: {self.visitor_info.supplier}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                            if self.visitor_info.is_group_visit:
                                message += f"\nGroup size: {self.visitor_info.total_members}"
                                for idx, member in enumerate(self.visitor_info.group_members, 2):
                                    message += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                            await self.ai.send_message_to_host(chat_id, access_token, message)
                    except Exception as e:
                        print(f"Error in Teams notification process: {e}")
                    
                    return "Your registration is complete."
                    
                elif user_input.lower() == "edit":
                    self.current_step = "supplier"
                    context["current_step"] = self.current_step
                    ai_msg = await self.get_ai_response(user_input, context)
                    supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                    return f"{ai_msg or STEP_PROMPTS['vendor_supplier']}\n{supplier_list}"
                else:
                    # Show summary again
                    summary = f"Supplier: {self.visitor_info.supplier}\nName: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                    if self.visitor_info.is_group_visit:
                        summary += f"\nGroup size: {self.visitor_info.total_members}"
                        for idx, member in enumerate(self.visitor_info.group_members, 2):
                            summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                    return f"{STEP_PROMPTS['vendor_confirm']}\n{summary}"
            elif self.current_step == "complete":
                return "Your registration is complete."

        # Generate AI response for the current step
        context = {
            "current_step": self.current_step,
            **self.visitor_info.to_dict()
        }
        return await self.get_ai_response(user_input, context)
    
    async def get_ai_response(self, user_input: str, context: dict) -> str:
        """Get a response from the AI model based on the current context"""
        # Use synchronous version for simplicity
        return self.ai.process_visitor_input(user_input, context)

    async def run(self):
        # Display hardcoded welcome message
        from prompts import HARDCODED_WELCOME
        print(f"\nDPL: {HARDCODED_WELCOME}")
        
        while True:
            if self.current_step == "complete":
                print("DPL: Please wait...")
                await asyncio.sleep(2)  # Give user time to read the completion message
                self.reset()
                print(f"\nDPL: {HARDCODED_WELCOME}")
                continue

            user_input = input("You: ").strip()
            if user_input.lower() in ["quit", "exit"]:
                goodbye_context = {"current_step": "complete", "is_exit": True}
                goodbye_response = self.ai.process_visitor_input("quit", goodbye_context)
                print(f"\nDPL: {goodbye_response}")
                break
            
            response = await self.process_input(user_input)
            print(f"\nDPL: {response}")
            
            # After printing response, if we're in complete state,
            # don't wait for user input before resetting

    async def handle_scheduled_host_step(self, user_input: str) -> str:
        """Handle the host selection step for pre-scheduled meetings"""
        # If in employee selection mode, handle the selection
        if self.employee_selection_mode:
            selected_employee = await self.ai.handle_employee_selection(user_input, self.employee_matches)
            if selected_employee:
                self.visitor_info.host_confirmed = selected_employee["displayName"]
                self.visitor_info.host_email = selected_employee["email"]
                # Reset selection mode
                self.employee_selection_mode = False
                self.employee_matches = []
                
                # Check for scheduled meetings - ensure timezone-aware datetime
                current_time = datetime.now(timezone.utc)
                meetings = await self.ai.get_scheduled_meetings(
                    self.visitor_info.host_email,
                    self.visitor_info.visitor_name,
                    current_time
                )
                
                # First verify if visitor email matches any meeting attendees
                matched_meetings = []
                if meetings:
                    for meeting in meetings:
                        attendees = meeting['original_event'].get('attendees', [])
                        for attendee in attendees:
                            email = attendee.get('emailAddress', {}).get('address', '')
                            if email == self.visitor_info.visitor_email:
                                matched_meetings.append(meeting)
                                break
                
                if not matched_meetings:
                    self.current_step = "scheduled_confirm"
                    return "No scheduled meetings found with your email address. Would you like to check in as a guest instead?\n1. Yes, check in as guest\n2. No, re-enter host name\n\nType '1' or '2' to proceed."
                
                # Found matching scheduled meetings
                self.visitor_info.scheduled_meeting = matched_meetings[0]  # Take the first matching meeting
                self.current_step = "scheduled_confirm"
                
                # Get the start and end time from original event
                event = matched_meetings[0]['original_event']
                start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                
                # Convert to Pakistan time (+5)
                pk_start = start_time + timedelta(hours=5)
                pk_end = end_time + timedelta(hours=5)
                
                meeting_info = (
                    f"Found your scheduled meeting:\n"
                    f"Time: {pk_start.strftime('%I:%M %p')} - {pk_end.strftime('%I:%M %p')}\n"
                    f"Purpose: {matched_meetings[0]['purpose']}\n\n"
                    f"Type 'confirm' to proceed or 'back' to re-enter the host name."
                )
                return meeting_info
            elif user_input == "0":
                # User wants to search for a different name
                self.employee_selection_mode = False
                self.employee_matches = []
                return "Please enter a different name."
            else:
                # Invalid selection, show options again
                options = "Please select a valid number:\n"
                for i, emp in enumerate(self.employee_matches, 1):
                    dept = emp.get("department", "Unknown Department")
                    options += f"  {i}. {emp['displayName']} ({dept})\n"
                options += "  0. None of these / Enter a different name"
                return options

        # Check if user chose to proceed as guest
        if user_input == "1" and self.current_step == "scheduled_confirm":
            # Convert to guest flow
            self.visitor_info.visitor_type = "guest"
            self.current_step = "purpose"
            return "What is the purpose of your visit?"
        elif user_input == "2" and self.current_step == "scheduled_confirm":
            self.current_step = "scheduled_host"
            return "Please enter your host's name."

        # Not in selection mode - search for the host
        employee = await self.ai.search_employee(user_input)
        if isinstance(employee, dict):
            self.visitor_info.host_confirmed = employee["displayName"]
            self.visitor_info.host_email = employee["email"]
            
            # Check for scheduled meetings - ensure timezone-aware datetime
            current_time = datetime.now(timezone.utc)
            meetings = await self.ai.get_scheduled_meetings(
                self.visitor_info.host_email,
                self.visitor_info.visitor_name,
                current_time
            )
            
            # First verify if visitor email matches any meeting attendees
            matched_meetings = []
            if meetings:
                for meeting in meetings:
                    attendees = meeting['original_event'].get('attendees', [])
                    for attendee in attendees:
                        email = attendee.get('emailAddress', {}).get('address', '')
                        if email == self.visitor_info.visitor_email:
                            matched_meetings.append(meeting)
                            break
            
            if not matched_meetings:
                self.current_step = "scheduled_confirm"
                return "No scheduled meetings found with your email address. Would you like to check in as a guest instead?\n1. Yes, check in as guest\n2. No, re-enter host name\n\nType '1' or '2' to proceed."
            
            # Found matching scheduled meetings
            self.visitor_info.scheduled_meeting = matched_meetings[0]  # Take the first matching meeting
            self.current_step = "scheduled_confirm"
            
            # Get the start and end time from original event
            event = matched_meetings[0]['original_event']
            start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
            
            # Convert to Pakistan time (+5)
            pk_start = start_time + timedelta(hours=5)
            pk_end = end_time + timedelta(hours=5)
            
            meeting_info = (
                f"Found your scheduled meeting:\n"
                f"Time: {pk_start.strftime('%I:%M %p')} - {pk_end.strftime('%I:%M %p')}\n"
                f"Purpose: {matched_meetings[0]['purpose']}\n\n"
                f"Type 'confirm' to proceed or 'back' to re-enter the host name."
            )
            return meeting_info
        elif isinstance(employee, list):
            self.employee_selection_mode = True
            self.employee_matches = employee
            options = "I found multiple potential matches. Please select one by number:\n"
            for i, emp in enumerate(employee, 1):
                dept = emp.get("department", "Unknown Department")
                options += f"  {i}. {emp['displayName']} ({dept})\n"
            options += "  0. None of these / Enter a different name"
            return options
        else:
            return "No matches found. Please enter a different name."

    async def get_ai_response(self, user_input: str, context: dict) -> str:
        """Get a response from the AI model based on the current context"""
        # Use synchronous version for simplicity
        return self.ai.process_visitor_input(user_input, context)

class MessageRequest(BaseModel):
    message: str
    current_step: Optional[str] = None
    visitor_info: Optional[dict] = None

class MessageResponse(BaseModel):
    response: str
    next_step: str
    visitor_info: dict

@app.post("/process-message/", response_model=MessageResponse)
async def process_message(request: Request, message_req: MessageRequest):
    """Handle visitor message processing with proper error handling and CORS."""
    try:
        receptionist = DPLReceptionist()
        
        # Restore state from frontend if provided
        if message_req.current_step:
            receptionist.current_step = message_req.current_step
            
        if message_req.visitor_info:
            # Restore all visitor info attributes
            for k, v in message_req.visitor_info.items():
                if hasattr(receptionist.visitor_info, k):
                    setattr(receptionist.visitor_info, k, v)
            
            # Restore employee selection mode and matches if needed
            if message_req.visitor_info.get('employee_selection_mode'):
                receptionist.employee_selection_mode = True
                receptionist.employee_matches = message_req.visitor_info.get('employee_matches', [])

        # Process the message
        response = await receptionist.process_input(message_req.message)

        # Get updated visitor info
        visitor_info = {}
        if hasattr(receptionist.visitor_info, 'to_dict'):
            visitor_info = receptionist.visitor_info.to_dict()
        else:
            visitor_info = {k: v for k, v in vars(receptionist.visitor_info).items() 
                          if not k.startswith('_')}
        
        # Add state info
        visitor_info['employee_selection_mode'] = receptionist.employee_selection_mode
        visitor_info['employee_matches'] = receptionist.employee_matches
        
        # Handle complete state
        if receptionist.current_step == 'complete':
            visitor_info['registration_completed'] = True
            
        return MessageResponse(
            response=response,
            next_step=receptionist.current_step,
            visitor_info=visitor_info
        )

    except Exception as e:
        print(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

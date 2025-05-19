import os
import json
import requests
import asyncio
from typing import Dict, Any, Optional, List
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.attendee import Attendee
from msgraph.generated.models.location import Location
from msgraph.generated.models.attendee_base import AttendeeBase as AttendeeType
from msgraph.generated.models.location_type import LocationType
from fuzzywuzzy import fuzz
from dotenv import load_dotenv
from prompts import SYSTEM_PERSONALITY, STEP_PROMPTS, RESPONSE_TEMPLATES, FLOW_CONSTRAINTS
from datetime import datetime, timedelta
from msal import PublicClientApplication
import threading
import time

# Load environment variables
load_dotenv()

# Microsoft Graph credentials
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

class AIReceptionist:
    def __init__(self):
        self.graph_client = self._initialize_graph_client()
        self.ollama_url = "http://localhost:11434/api/generate"
        self._chat_id_cache = {}  # In-memory cache for chat IDs
        self._chat_id_cache_lock = threading.Lock()
        self._system_account_email = "saadsaad@dpl660.onmicrosoft.com"

    def _initialize_graph_client(self) -> Optional[GraphServiceClient]:
        """Initialize the Microsoft Graph client with proper scope."""
        try:
            if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
                print("Error: Missing required Azure AD credentials in environment variables")
                return None
            credential = ClientSecretCredential(
                tenant_id=TENANT_ID,
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET
            )
            # Only use .default scope for client credentials flow
            scopes = [
                'https://graph.microsoft.com/.default'
            ]
            client = GraphServiceClient(credentials=credential, scopes=scopes)
            print("Successfully connected to Microsoft Graph API")
            return client
        except Exception as e:
            print(f"Error initializing Graph client: {e}")
            return None

    def process_visitor_input(self, user_input: str, context: Dict[str, Any]) -> str:
        formatted_context = {
            "visitor_type": context.get("visitor_type", ""),
            "visitor_name": context.get("visitor_name", ""),
            "visitor_cnic": context.get("visitor_cnic", ""),
            "visitor_phone": context.get("visitor_phone", ""),
            "host_requested": context.get("host_requested", ""),
            "host_confirmed": context.get("host_confirmed", ""),
            "purpose": context.get("purpose", ""),
            "current_step": context.get("current_step", "unknown"),
            "supplier": context.get("supplier", ""),
            "group_size": context.get("total_members", 1),
            "members_collected": len(context.get("group_members", [])),
            "next_number": len(context.get("group_members", [])) + 2
        }

        current_step = formatted_context["current_step"]
        step_prompt = STEP_PROMPTS.get(current_step, "")

        prompt = f"{SYSTEM_PERSONALITY}\n\n{FLOW_CONSTRAINTS}\n\n{step_prompt}\n\n"
        prompt += "Current context:\n"
        for key, value in formatted_context.items():
            if value:
                prompt += f"- {key}: {value}\n"
        prompt += f"\nVisitor: {user_input}\n\nAssistant:"

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": "llama3",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 200
                }
            )
            response.raise_for_status()
            ai_response = response.json().get("response", "").strip()
            if not ai_response:
                return self._get_fallback_response(current_step, formatted_context)
            return ai_response
        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            return self._get_fallback_response(current_step, formatted_context)

    def _get_fallback_response(self, step: str, context: Dict[str, Any]) -> str:
        name = context.get("visitor_name", "")
        name_greeting = f", {name}" if name else ""
        if step in STEP_PROMPTS:
            return STEP_PROMPTS[step].split("\n")[1].strip()
        return RESPONSE_TEMPLATES["error"]

    async def search_employee(self, name: str) -> Optional[Dict[str, Any]]:
        """Search for an employee by name using Microsoft Graph API."""
        try:
            if self.graph_client is None:
                print("Graph client not initialized. Cannot search for employees.")
                return None

            # Attempt to get user details with retries
            retries = 3
            delay = 2  # Initial delay in seconds
            last_error = None

            while retries > 0:
                try:
                    select_params = ["displayName", "mail", "department", "jobTitle", "id"]
                    result = await self.graph_client.users.get()

                    if not result or not result.value:
                        print("No users found in the organization")
                        return None
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    print(f"Attempt {4-retries}/3: Error querying users: {e}")
                    last_error = e
                    retries -= 1
                    if retries > 0:
                        print(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        print("Failed to query users after 3 attempts")
                        return None

            if last_error and retries == 0:
                return None

            # Search for matches
            search_name = name.lower().strip()
            matches = []
            
            # First try exact match
            exact_matches = []
            for user in result.value:
                if not user.display_name or not user.mail:
                    continue
                    
                display_name = user.display_name.lower()
                if search_name == display_name:
                    exact_matches.append({
                        "displayName": user.display_name,
                        "email": user.mail,
                        "department": user.department or "Unknown Department",
                        "jobTitle": user.job_title or "Unknown Title",
                        "id": user.id,
                        "score": 100
                    })
            
            if exact_matches:
                return exact_matches[0]  # Return first exact match
                
            # If no exact match, try fuzzy matching
            for user in result.value:
                if not user.display_name or not user.mail:
                    continue
                    
                display_name = user.display_name.lower()
                name_parts = display_name.split()
                
                # Different scoring methods
                scores = [
                    fuzz.ratio(search_name, display_name),  # Exact match score
                    fuzz.partial_ratio(search_name, display_name),  # Partial match score
                    fuzz.token_sort_ratio(search_name, display_name),  # Word order independent score
                    max((fuzz.ratio(search_name, part) for part in name_parts), default=0)  # Best single word match
                ]
                
                # Take highest score from any method
                best_score = max(scores)
                
                if best_score >= 60:  # Threshold for considering it a match
                    matches.append({
                        "displayName": user.display_name,
                        "email": user.mail,
                        "department": user.department or 'Unknown Department',
                        "jobTitle": user.job_title or 'Unknown Title',
                        "id": user.id,
                        "score": best_score
                    })

            matches.sort(key=lambda x: x["score"], reverse=True)
            for match in matches:
                match.pop("score", None)

            if not matches:
                print(f"No matches found for name: {name}")
                return None
            elif len(matches) == 1:
                print(f"Found single match: {matches[0]['displayName']} ({matches[0]['email']})")
                return matches[0]
            else:
                print(f"Found {len(matches)} matches")
                return matches

        except Exception as e:
            print(f"Error searching employee: {str(e)}")
            return None

    def get_system_account_token(self) -> str:
        CLIENT_ID = os.getenv("CLIENT_ID")
        TENANT_ID = os.getenv("TENANT_ID")
        AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
        SCOPES = ["Chat.ReadWrite", "User.Read", "Chat.Create"]
        app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
        accounts = app.get_accounts(username=self._system_account_email)
        result = None
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result or 'access_token' not in result:
            print("No cached token found or token expired, acquiring interactively...")
            result = app.acquire_token_interactive(scopes=SCOPES, login_hint=self._system_account_email)
        if not result or 'access_token' not in result or not result['access_token']:
            raise Exception("Failed to acquire system account access token.")
        print(f"[DEBUG] Acquired access token: {result['access_token'][:10]}... (truncated)")
        return result['access_token']

    def get_user_id(self, email: str, access_token: str) -> str:
        if not access_token:
            raise Exception("Access token is empty when trying to get user ID.")
        url = f"https://graph.microsoft.com/v1.0/users/{email}"
        headers = {'Authorization': f'Bearer {access_token}'}
        print(f"[DEBUG] Getting user ID for: {email} with token: {access_token[:10]}... (truncated)")
        response = requests.get(url, headers=headers)
        if response.status_code == 401 or response.status_code == 403:
            print(f"[ERROR] Permission denied or unauthorized for user {email}. Response: {response.text}")
        response.raise_for_status()
        return response.json()['id']

    def create_or_get_chat(self, host_user_id: str, system_user_id: str, access_token: str) -> str:
        if not access_token:
            raise Exception("Access token is empty when trying to create or get chat.")
        cache_key = tuple(sorted([host_user_id, system_user_id]))
        with self._chat_id_cache_lock:
            if cache_key in self._chat_id_cache:
                return self._chat_id_cache[cache_key]
        url = "https://graph.microsoft.com/v1.0/chats"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        body = {
            "chatType": "oneOnOne",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{host_user_id}')"
                },
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{system_user_id}')"
                }
            ]
        }
        print(f"[DEBUG] Creating chat between {host_user_id} and {system_user_id}")
        response = requests.post(url, json=body, headers=headers)
        if response.status_code == 409:
            chat_id = self.find_existing_one_on_one_chat(host_user_id, system_user_id, access_token)
            if chat_id:
                with self._chat_id_cache_lock:
                    self._chat_id_cache[cache_key] = chat_id
                return chat_id
            else:
                raise Exception("Could not find existing chat after 409 response.")
        response.raise_for_status()
        chat_id = response.json()['id']
        with self._chat_id_cache_lock:
            self._chat_id_cache[cache_key] = chat_id
        return chat_id

    def find_existing_one_on_one_chat(self, host_user_id: str, system_user_id: str, access_token: str) -> str:
        if not access_token:
            raise Exception("Access token is empty when trying to find existing chat.")
        url = "https://graph.microsoft.com/v1.0/me/chats?$filter=chatType eq 'oneOnOne'"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"[ERROR] Failed to list chats: {response.text}")
            return None
        chats = response.json().get('value', [])
        for chat in chats:
            members_url = f"https://graph.microsoft.com/v1.0/chats/{chat['id']}/members"
            members_resp = requests.get(members_url, headers=headers)
            if members_resp.status_code != 200:
                continue
            members = members_resp.json().get('value', [])
            member_ids = set(m['userId'] for m in members if 'userId' in m)
            if {host_user_id, system_user_id} == member_ids:
                return chat['id']
        return None

    def send_message_to_host(self, chat_id: str, access_token: str, message: str):
        """Send a Teams message with improved error handling and logging."""
        if not access_token:
            raise Exception("Access token is empty when trying to send message.")
            
        if not chat_id:
            raise Exception("Chat ID is empty when trying to send message.")
            
        if not message:
            raise Exception("Message content is empty.")
            
        url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        body = {
            "body": {
                "content": message,
                "contentType": "text"
            }
        }
        
        print(f"[DEBUG] Attempting to send message to chat {chat_id}")
        try:
            response = requests.post(url, json=body, headers=headers, timeout=10)  # Add timeout
            
            if response.status_code in [401, 403]:
                print(f"[ERROR] Permission denied or unauthorized. Response: {response.text}")
                print("[DEBUG] This usually means the access token is invalid or expired")
                raise Exception("Authorization failed when sending Teams message")
                
            elif response.status_code == 404:
                print(f"[ERROR] Chat not found. Chat ID: {chat_id}")
                raise Exception("Chat not found")
                
            elif response.status_code >= 500:
                print(f"[ERROR] Teams service error. Status: {response.status_code}")
                raise Exception("Teams service error")
                
            response.raise_for_status()
            
            result = response.json()
            print("[DEBUG] Message sent successfully")
            return result
            
        except requests.exceptions.Timeout:
            print("[ERROR] Request timed out when sending Teams message")
            raise Exception("Teams message request timed out")
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error when sending Teams message: {str(e)}")
            raise Exception(f"Network error: {str(e)}")
            
        except Exception as e:
            print(f"[ERROR] Unexpected error when sending Teams message: {str(e)}")
            raise

    async def schedule_meeting(self, host_email: str, visitor_name: str, purpose: str) -> bool:
        """Schedule a calendar meeting using Microsoft Graph API and notify the host via Teams."""
        try:
            current_time = datetime.utcnow() + timedelta(minutes=5)
            current_time = current_time.replace(minute=(current_time.minute // 5) * 5, second=0, microsecond=0)
            end_time = current_time + timedelta(minutes=25)

            visitor_id = f"{visitor_name.lower().replace(' ', '-')}-{current_time.strftime('%Y%m%d%H%M')}"

            email_address = EmailAddress(
                address=host_email,
                name=host_email
            )
            attendee = Attendee(
                email_address=email_address,
                type=1
            )

            body_content = f"""
            <h2>Guest Visit Details</h2>
            <p><strong>Guest Name:</strong> {visitor_name}</p>
            <p><strong>Visit Purpose:</strong> {purpose}</p>
            <p><strong>Visitor ID:</strong> {visitor_id}</p>
            <p><strong>Meeting Duration:</strong> 25 minutes</p>
            <p><strong>Meeting Type:</strong> In-person Visit</p>
            """
            body = ItemBody(
                content_type="HTML",
                content=body_content
            )

            start = DateTimeTimeZone(
                date_time=current_time.isoformat(),
                time_zone="UTC"
            )
            end = DateTimeTimeZone(
                date_time=end_time.isoformat(),
                time_zone="UTC"
            )

            location = Location(
                display_name="DPL Office",
                location_type=0
            )

            event = Event(
                subject=f"Meeting with {visitor_name} - {purpose}",
                start=start,
                end=end,
                body=body,
                attendees=[attendee],
                location=location,
                is_online_meeting=True,
                online_meeting_provider="teamsForBusiness",
                allow_new_time_proposals=False,
                reminder_minutes_before_start=15
            )

            await self.graph_client.users.by_user_id(host_email).events.post(event)
            print(f"Successfully scheduled meeting for {visitor_name} with {host_email}")

            # --- Teams Notification ---
            try:
                access_token = self.get_system_account_token()
                if not access_token:
                    raise Exception("Access token is empty after acquisition!")
                host_user_id = self.get_user_id(host_email, access_token)
                system_user_id = self.get_user_id(self._system_account_email, access_token)
                chat_id = self.create_or_get_chat(host_user_id, system_user_id, access_token)
                message = (
                    f"A visitor has arrived at reception to meet you: {visitor_name}. "
                    "Please check the Teams calendar for details."
                )
                self.send_message_to_host(chat_id, access_token, message)
                print(f"Teams notification sent to {host_email}")
            except Exception as e:
                print(f"Error sending Teams notification: {e}")

            return True

        except Exception as e:
            print(f"Error scheduling meeting: {str(e)}")
            return False
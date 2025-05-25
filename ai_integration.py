import os
import json
import requests
import asyncio
import boto3
from graph_client import create_graph_client
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import msal
from msal import PublicClientApplication
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.attendee import Attendee
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.location import Location
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.core import GraphClientFactory
from msgraph.core.client import GraphClient
from msgraph.core.requests.base_request_builder import BaseRequestBuilder
from azure.core.credentials import TokenCredential
from fuzzywuzzy import fuzz
from dotenv import load_dotenv
from prompts import SYSTEM_PERSONALITY, STEP_PROMPTS, RESPONSE_TEMPLATES, FLOW_CONSTRAINTS
import threading
import time
from kiota_abstractions.request_information import RequestInformation
from kiota_abstractions.method import Method
import boto3

# Load environment variables
load_dotenv()

# Microsoft Graph credentials
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

class AIReceptionist:
    def __init__(self):
        self._system_account_email = "SaadSaad@DPL660.onmicrosoft.com"  # Admin account for application permissions
        self.graph_client = self._initialize_graph_client()
        self._chat_id_cache = {}  # In-memory cache for chat IDs
        self._chat_id_cache_lock = threading.Lock()
        self.bedrock_client = self._initialize_bedrock_client()

    def _initialize_graph_client(self) -> Optional[GraphServiceClient]:
        """Initialize the Microsoft Graph client with application permissions."""
        try:
            if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
                print("Error: Missing required Azure AD credentials in environment variables")
                return None

            print(f"Initializing Graph client with admin account: {self._system_account_email}")
            
            try:
                # Create credential object
                credential = ClientSecretCredential(
                    tenant_id=TENANT_ID,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET
                )
                
                # Define scopes for application permissions
                scopes = ['https://graph.microsoft.com/.default']
                
                # Create Graph client with scopes
                graph_client = GraphServiceClient(credentials=credential, scopes=scopes)
                
                # Test that the client works
                try:
                    users = graph_client.users.get()
                    print("Successfully initialized Microsoft Graph client")
                    return graph_client
                except Exception as e:
                    print(f"Error testing Graph client: {e}")
                    return None
                    
            except Exception as e:
                print(f"Error creating Graph client: {e}")
                return None
            
        except Exception as e:
            print(f"Error initializing Graph client: {e}")
            return None

    def _initialize_bedrock_client(self) -> Optional[Any]:
        """Initialize the AWS Bedrock client."""
        try:
            # Get AWS configuration from environment variables
            aws_region = os.getenv("AWS_REGION", "us-east-1")
            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

            if not all([aws_access_key, aws_secret_key]):
                print("Error: Missing required AWS credentials in environment variables")
                return None

            # Initialize the Bedrock client with credentials
            client = boto3.client(
                "bedrock-runtime",
                region_name=aws_region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key
            )
            
            print(f"Successfully initialized AWS Bedrock client in region {aws_region}")
            return client
        except Exception as e:
            print(f"Error initializing Bedrock client: {e}")
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
            "next_number": len(context.get("group_members", [])) + 2,
            "flow_type": context.get("visitor_type", ""),  # Add flow type for context
            "validation_error": context.get("validation_error", ""),  # Add validation errors
            "previous_step": context.get("previous_step", "")  # Track previous step
        }

        current_step = formatted_context["current_step"]
        step_prompt = STEP_PROMPTS.get(current_step, "")
        
        # Enhanced prompt construction for more natural conversation
        prompt = f"{SYSTEM_PERSONALITY}\n\n{FLOW_CONSTRAINTS}\n\n"
        
        # Add step-specific guidance
        if step_prompt:
            prompt += f"Current step requirements: {step_prompt}\n\n"
        
        # Add conversation context
        prompt += "Current conversation state:\n"
        relevant_context = {
            k: v for k, v in formatted_context.items() 
            if v and k not in ['validation_error', 'previous_step']
        }
        for key, value in relevant_context.items():
            prompt += f"- {key}: {value}\n"
            
        # Add validation context if there was an error
        if formatted_context.get('validation_error'):
            prompt += f"\nValidation error: {formatted_context['validation_error']}\n"
            
        # Add flow state context
        if formatted_context.get('flow_type'):
            flow_type = formatted_context['flow_type']
            if flow_type == 'guest':
                prompt += "\nCurrent flow: Guest registration - Collecting visitor details\n"
            elif flow_type == 'vendor':
                # For vendor flow, use step prompts directly without AI generation
                prompt_text = STEP_PROMPTS.get(current_step, "")
                if prompt_text:
                    if current_step.startswith('vendor_member_'):
                        member_num = formatted_context.get("member_number", "")
                        prompt_text = prompt_text.replace("{number}", str(member_num))
                    return prompt_text
                return self._get_fallback_response(current_step, formatted_context)
            elif flow_type == 'prescheduled':
                prompt += "\nCurrent flow: Pre-scheduled meeting - Verifying appointment\n"
                
        prompt += f"\nVisitor: {user_input}\n\nAssistant:"

        try:
            if not self.bedrock_client:
                print("Bedrock client not initialized")
                return self._get_fallback_response(current_step, formatted_context)

            # Format the prompt
            formatted_prompt = f"""<|im_start|>system
{SYSTEM_PERSONALITY}

Current context:
Step: {current_step}
{formatted_context}

User message: {user_input}

{FLOW_CONSTRAINTS}"""

            request_payload = {
                "prompt": formatted_prompt,
                "max_gen_len": 512,
                "temperature": 0.2,
                "top_p": 0.9
            }

            # Convert to JSON with proper encoding
            request_body = json.dumps(request_payload, ensure_ascii=False).encode('utf-8')
            
            try:
                # Get model ID from environment variables
                model_id = os.getenv("AWS_BEDROCK_MODEL_ID", "anthropic.claude-instant-v1")
                
                print(f"[DEBUG] Invoking Bedrock model {model_id}")
                print(f"[DEBUG] Request payload: {json.dumps(request_payload, indent=2)}")

                # Invoke Bedrock model
                try:
                    response = self.bedrock_client.invoke_model(
                        modelId=model_id,
                        contentType="application/json",
                        accept="application/json",
                        body=request_body
                    )

                    # Parse response
                    response_body = json.loads(response.get('body').read().decode('utf-8'))
                    print(f"[DEBUG] Bedrock response: {json.dumps(response_body, indent=2)}")

                    # Extract and validate response
                    if "completion" in response_body:
                        generation = response_body["completion"]
                    elif "generation" in response_body:
                        generation = response_body["generation"]
                    else:
                        print("[ERROR] Unexpected response format from Bedrock")
                        return self._get_fallback_response(current_step, formatted_context)
                        
                    generation = generation.strip()
                    if "GENERATION" in generation or not generation:
                        print("[ERROR] Invalid or empty generation from Bedrock")
                        return self._get_fallback_response(current_step, formatted_context)

                    generation = generation.strip()
                    if not generation:
                        print("[ERROR] Empty generation from Bedrock")
                        return self._get_fallback_response(current_step, formatted_context)

                    # For vendor flow, always use step prompts directly
                    if current_step.startswith('vendor_'):
                        prompt_text = STEP_PROMPTS.get(current_step)
                        if not prompt_text:
                            print(f"[ERROR] No step prompt found for {current_step}")
                            return self._get_fallback_response(current_step, formatted_context)
                            
                        # Handle member number replacement
                        if current_step.startswith('vendor_member_'):
                            member_num = formatted_context.get("member_number", "")
                            return prompt_text.replace("{number}", str(member_num))
                        return prompt_text
                        
                    # Use the step prompts for other flows
                    if current_step in STEP_PROMPTS:
                        prompt_text = STEP_PROMPTS[current_step]
                        
                        # Don't personalize scheduled steps
                        if current_step.startswith('scheduled_'):
                            generation = prompt_text
                        # Personalize guest flow responses with name if available
                        else:
                            if formatted_context.get("visitor_name"):
                                visitor_name = formatted_context["visitor_name"]
                                generation = f"{visitor_name}, {prompt_text}"
                            else:
                                generation = prompt_text
                    
                    # Ensure we only return the first line of any response
                    generation = generation.split('\n')[0].strip()

                except Exception as e:
                    print(f"[ERROR] Error invoking Bedrock model: {str(e)}")
                    return self._get_fallback_response(current_step, formatted_context)
                
                ai_response = generation
                return ai_response

            except ClientError as e:
                print(f"[ERROR] Bedrock ClientError: {str(e)}")
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                print(f"[ERROR] Error code: {error_code}")
                return self._get_fallback_response(current_step, formatted_context)

        except Exception as e:
            print(f"[ERROR] Error in process_visitor_input: {str(e)}")
            return self._get_fallback_response(current_step, formatted_context)

    def _get_fallback_response(self, step: str, context: Dict[str, Any]) -> str:
        """Get a fallback response when AI fails, but try to keep it natural"""
        name = context.get("visitor_name", "")
        name_greeting = f", {name}" if name else ""
        
        # Add context for better fallback responses
        validation_error = context.get("validation_error", "")
        flow_type = context.get("visitor_type", "")
        member_num = context.get("member_number")
        
        # If there's a validation error, provide a more helpful message
        if validation_error:
            if validation_error == "cnic":
                if member_num:
                    return f"Please provide a valid CNIC for member {member_num} in the format: 12345-1234567-1."
                return f"I'm sorry{name_greeting}, but the CNIC format should be like this: 12345-1234567-1. Could you please try again?"
            elif validation_error == "phone":
                if member_num:
                    return f"Please provide a valid phone number for member {member_num} in the format: +923001234567 or 03001234567."
                return f"I need a valid phone number{name_greeting}. Please provide it in the format: +923001234567 or 03001234567"
            elif validation_error == "name":
                if member_num:
                    return f"Please provide a valid name for member {member_num} (letters and spaces only)."
                return "Please enter a valid name using only letters and spaces."
                
        # Handle vendor-specific steps
        if step.startswith("vendor_"):
            prompt = STEP_PROMPTS.get(step, "")
            if member_num and "{number}" in prompt:
                prompt = prompt.replace("{number}", str(member_num))
            return prompt

        # Fallback to standard prompts
        if step in STEP_PROMPTS:
            prompt_text = STEP_PROMPTS[step]
            # Handle both single-line and multi-line prompts
            if "\n" in prompt_text:
                prompt = prompt_text.split("\n")[1].strip()
            else:
                prompt = prompt_text.strip()
            
            if name:
                # Make it more personal if we have the name
                prompt = f"{name}, {prompt.lower()}"
            return prompt
            
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
                # Return the match as a list so it can be handled like multiple matches
                return [matches[0]]  # This will trigger the selection prompt
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

    async def get_scheduled_meetings(self, host_email: str, visitor_name: str, check_time: datetime) -> Optional[List[Dict[str, Any]]]:
        """Check host's calendar for scheduled meetings using Microsoft Graph API."""
        try:
            # Initialize MSAL client
            app = msal.ConfidentialClientApplication(
                CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{TENANT_ID}",
                client_credential=CLIENT_SECRET,
            )

            # Get token
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

            if "access_token" not in result:
                print("Could not acquire token")
                return None

            token = result["access_token"]
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Ensure check_time is timezone-aware UTC
            if check_time.tzinfo is None:
                check_time = check_time.replace(tzinfo=timezone.utc)
            
            # Convert UTC to Pakistan time for day boundary calculation
            pk_tz_offset = timedelta(hours=5)
            check_time_pk = check_time.astimezone(timezone.utc) + pk_tz_offset
            
            # Get start and end of day in Pakistan time
            start_of_day_pk = check_time_pk.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day_pk = check_time_pk.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Convert back to UTC for API call
            start_of_day_utc = (start_of_day_pk - pk_tz_offset).astimezone(timezone.utc)
            end_of_day_utc = (end_of_day_pk - pk_tz_offset).astimezone(timezone.utc)

            # Format times for Microsoft Graph API
            start_time = start_of_day_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            end_time = end_of_day_utc.strftime('%Y-%m-%dT%H:%M:%S.999Z')

            # Prepare calendar API call
            url = (
                f"https://graph.microsoft.com/v1.0/users/{host_email}/calendar/calendarView"
                f"?startDateTime={start_time}&endDateTime={end_time}"
                f"&$orderby=start/dateTime&$top=20"
            )

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                events = response.json().get("value", [])
                meetings = []
                check_time_pk_hour = check_time_pk.hour

                for event in events:
                    # Only consider events that have the visitor's email in the attendee list
                    attendees = event.get("attendees", [])
                    visitor_email_found = False
                    for attendee in attendees:
                        email = attendee.get("emailAddress", {}).get("address", "")
                        if email:  # Only check if email exists
                            if "@" in email:  # Basic email validation
                                visitor_email_found = True
                                break
                    
                    if not visitor_email_found:
                        continue  # Skip this event if visitor's email not found

                    start = event.get("start", {}).get("dateTime")
                    if start:
                        # Parse the event time as UTC and convert to Pakistan time
                        event_time_utc = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        event_time_pk = event_time_utc + pk_tz_offset
                        
                        # Only include meetings in current hour range
                        time_match = abs(event_time_pk.hour - check_time_pk_hour) <= 1
                        
                        if time_match:
                            meeting = {
                                "scheduled_time": event_time_pk.strftime("%I:%M %p"),
                                "purpose": event.get("subject", "Pre-scheduled meeting"),
                                "original_event": event
                            }
                            meetings.append(meeting)

                return meetings if meetings else None
            else:
                print(f"Error fetching calendar events: {response.status_code}")
                print(response.text)
                return None

        except Exception as e:
            print(f"Error checking calendar: {str(e)}")
            return None

    async def handle_employee_selection(self, user_input: str, employee_matches: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Handle employee selection from a list of matches"""
        print(f"[DEBUG] Processing employee selection input: {user_input}")
        print(f"[DEBUG] Available matches: {len(employee_matches)} employees")
        
        if user_input.isdigit():
            selection = int(user_input)
            if selection == 0:
                print("[DEBUG] User chose to enter a different name")
                return None
            if 1 <= selection <= len(employee_matches):
                selected = employee_matches[selection - 1]
                print(f"[DEBUG] Selected employee: {selected['displayName']}")
                return selected
        
        print(f"[DEBUG] Invalid selection: {user_input}")
        return None

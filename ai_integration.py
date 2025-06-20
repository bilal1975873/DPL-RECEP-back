import os
import json
import asyncio
import boto3
import msal
import requests
import logging
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from msgraph import GraphServiceClient
from graph_client import create_graph_client, search_users, get_users

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.attendee import Attendee
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.location import Location
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.chat_message import ChatMessage
from msgraph.generated.models.chat import Chat
from msgraph.generated.models.aad_user_conversation_member import AadUserConversationMember
from azure.core.credentials import TokenCredential
from rapidfuzz import fuzz
from dotenv import load_dotenv
from prompts import SYSTEM_PERSONALITY, STEP_PROMPTS, RESPONSE_TEMPLATES, FLOW_CONSTRAINTS
import threading
import time
from kiota_abstractions.request_information import RequestInformation
from kiota_abstractions.method import Method
from fastapi import HTTPException

# Load environment variables
load_dotenv()

# Microsoft Graph credentials
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

class AIReceptionist:
    def __init__(self):
        self._system_account_email = "SaadSaad@DPL660.onmicrosoft.com"  # Admin account for notifications
        self._chat_id_cache = {}  # In-memory cache for chat IDs
        self._chat_id_cache_lock = threading.Lock()
        self.bedrock_client = self._initialize_bedrock_client()
        self.graph_client = self._initialize_graph_client()

    def _initialize_graph_client(self) -> Optional[GraphServiceClient]:
        """Initialize the Microsoft Graph client with client credentials."""
        try:
            # Check for required credentials
            if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
                missing = []
                if not TENANT_ID: missing.append("TENANT_ID")
                if not CLIENT_ID: missing.append("CLIENT_ID")
                if not CLIENT_SECRET: missing.append("CLIENT_SECRET")
                logger.error(f"Missing required Microsoft Graph credentials: {', '.join(missing)}")
                return None

            logger.info("Initializing Graph client with application permissions...")
            client = create_graph_client(TENANT_ID, CLIENT_ID, CLIENT_SECRET)
            
            if client:
                logger.info("Successfully initialized Graph client")
            else:
                logger.error("Failed to initialize Graph client")
                
            return client
            
        except Exception as e:
            logger.error(f"Failed to initialize Graph client: {str(e)}")
            return None
            
    async def search_employee(self, search_term: str) -> Optional[List[Dict[str, Any]]]:
        """
        Search for employees using Microsoft Graph API.
        
        Args:
            search_term (str): Name or email to search for
            
        Returns:
            Optional[List[Dict[str, Any]]]: List of matching employees or None if search fails
        """
        if not self.graph_client:
            logger.error("Graph client not initialized")
            return None
        
        if not search_term:
            logger.error("Search term cannot be empty")
            return None
            
        try:
            logger.info(f"Searching for employee with term: {search_term}")
            results = await search_users(self.graph_client, search_term)
            
            if results:
                logger.info(f"Found {len(results)} matching employees")
            else:
                logger.warning("No employees found matching the search criteria")
                
            return results
            
        except Exception as e:
            logger.error(f"Failed to search employees: {str(e)}")
            return None
            
            # Check for required credentials
            if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
                missing = []
                if not TENANT_ID: missing.append("TENANT_ID")
                if not CLIENT_ID: missing.append("CLIENT_ID")
                if not CLIENT_SECRET: missing.append("CLIENT_SECRET")
                print(f"[ERROR] Missing required Azure AD credentials: {', '.join(missing)}")
                return None

            print("[DEBUG] Initializing Graph client...")
            
            try:
                # Create credential object for application permissions
                credential = ClientSecretCredential(
                    tenant_id=TENANT_ID,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET
                )
                
                # Create Graph client without scopes (using app permissions)
                graph_client = GraphServiceClient(credentials=credential)
                
                # Test the client with a simple request
                try:
                    print("[DEBUG] Testing Graph client connection...")
                    # Just get users with basic filtering
                    test = graph_client.users.get()
                    
                    print("[DEBUG] Graph API response received")
                    if test:
                        print("[DEBUG] Response object exists")
                        print(f"[DEBUG] Response type: {type(test)}")
                        print(f"[DEBUG] Response attributes: {dir(test)}")
                        if hasattr(test, 'value'):
                            print(f"[DEBUG] Found {len(test.value)} users")
                            if len(test.value) > 0:
                                print("[INFO] Successfully verified Graph client access")
                                return graph_client
                    
                    print("[ERROR] Graph client test failed - invalid response format")
                    return None
                except Exception as e:
                    error_msg = str(e)
                    print(f"[ERROR] Graph client test failed: {error_msg}")
                    print("[DEBUG] Full exception details:", e)
                    
                    if 'InvalidAuthenticationToken' in error_msg:
                        print("[ERROR] Invalid authentication token. Please verify:")
                        print("1. CLIENT_SECRET is correct and not expired")
                        print("2. The app registration exists in Azure AD")
                        print(f"3. Using correct TENANT_ID: {TENANT_ID}")
                    elif 'Authorization_RequestDenied' in error_msg:
                        print("[ERROR] Authorization denied. Please verify in Azure Portal:")
                        print("1. Application permissions are granted:")
                        print("   - User.Read.All")
                        print("   - Chat.Create")
                        print("   - Chat.ReadWrite")
                        print("2. Admin consent is granted for these permissions")
                        print(f"3. App ID {CLIENT_ID} is correct")
                    elif 'InvalidClient' in error_msg:
                        print(f"[ERROR] Invalid client. Current CLIENT_ID: {CLIENT_ID}")
                        print("Please verify in Azure Portal that this is the correct Application (client) ID")
                    elif 'ResourceNotFound' in error_msg:
                        print(f"[ERROR] Resource not found. Current TENANT_ID: {TENANT_ID}")
                        print("Please verify this is your Azure AD tenant ID")
                    elif 'Microsoft.Graph.' in error_msg:
                        print("[ERROR] Graph API error. Please verify:")
                        print("1. The Azure AD app has User.Read.All permission")
                        print("2. Admin consent is granted")
                        print("3. The account used has sufficient privileges")
                    
                    return None
                    
            except Exception as e:
                print(f"[ERROR] Failed to create Graph client: {str(e)}")
                return None
            
        except Exception as e:
            print(f"[ERROR] Unexpected error in Graph client initialization: {str(e)}")
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
            print(f"[DEBUG] Starting employee search for name: {name}")
            
            # Initialize Graph client with system credentials if not initialized
            if self.graph_client is None:
                print("[DEBUG] Graph client not initialized, initializing now...")
                self.graph_client = self._initialize_graph_client()
                if not self.graph_client:
                    print("[ERROR] Failed to initialize Graph client")
                    return None
                print("[DEBUG] Successfully initialized Graph client")

            # Attempt to get user details with retries
            retries = 3
            delay = 2  # Initial delay in seconds
            last_error = None

            while retries > 0:
                try:
                    print("[DEBUG] Querying users from Microsoft Graph API...")
                    # Use $select to get only needed fields and improve performance
                    select_params = ["displayName", "mail", "department", "jobTitle", "id"]
                    result = await self.graph_client.users.get()

                    if not result or not result.value:
                        print("[ERROR] No users found in the organization")
                        return None
                    
                    print(f"[DEBUG] Successfully retrieved {len(result.value)} users")
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    print(f"[ERROR] Attempt {4-retries}/3: Error querying users: {str(e)}")
                    last_error = e
                    retries -= 1
                    if retries > 0:
                        print(f"[DEBUG] Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        print("[ERROR] Failed to query users after 3 attempts")
                        return None

            if last_error and retries == 0:
                return None

            # Search for matches
            search_name = name.lower().strip()
            matches = []
            
            print(f"[DEBUG] Searching for matches with name: {search_name}")
            
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
                print(f"[DEBUG] Found exact match: {exact_matches[0]['displayName']}")
                return exact_matches[0]  # Return first exact match
                
            # If no exact match, try fuzzy matching
            print("[DEBUG] No exact match found, trying fuzzy matching...")
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
                    print(f"[DEBUG] Found fuzzy match: {user.display_name} (score: {best_score})")
                    matches.append({
                        "displayName": user.display_name,
                        "email": user.mail,
                        "department": user.department or 'Unknown Department',
                        "jobTitle": user.job_title or 'Unknown Title',
                        "id": user.id,
                        "score": best_score
                    })

            # Sort matches by score
            matches.sort(key=lambda x: x["score"], reverse=True)
            
            # Remove scores before returning
            for match in matches:
                match.pop("score", None)

            if not matches:
                print(f"[DEBUG] No matches found for name: {name}")
                return None
            elif len(matches) == 1:
                print(f"[DEBUG] Found single match: {matches[0]['displayName']} ({matches[0]['email']})")
                return matches[0]
            else:
                print(f"[DEBUG] Found {len(matches)} matches")
                return matches

        except Exception as e:
            print(f"[ERROR] Error in search_employee: {str(e)}")
            print(f"[ERROR] Stack trace:", exc_info=True)
            return None

    def get_system_account_token(self) -> str:
        """Get an access token using client credentials flow."""
        try:
            CLIENT_ID = os.getenv("CLIENT_ID")
            TENANT_ID = os.getenv("TENANT_ID")
            CLIENT_SECRET = os.getenv("CLIENT_SECRET")
            AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
            SCOPES = ["https://graph.microsoft.com/.default"]  # Use .default scope for application permissions

            # Initialize confidential client application for app authentication
            app = msal.ConfidentialClientApplication(
                client_id=CLIENT_ID,
                client_credential=CLIENT_SECRET,
                authority=AUTHORITY
            )

            # Get token using client credentials flow
            result = app.acquire_token_for_client(scopes=SCOPES)
            
            if not result or 'access_token' not in result:
                logger.error("Failed to acquire access token using client credentials")
                error_desc = result.get('error_description', 'No error description') if result else 'No result'
                logger.error(f"Error details: {error_desc}")
                raise Exception("Failed to acquire access token")

            logger.info(f"Successfully acquired access token: {result['access_token'][:10]}... (truncated)")
            return result['access_token']

        except Exception as e:
            logger.error(f"Error in get_system_account_token: {str(e)}", exc_info=True)
            raise Exception(f"Failed to acquire access token: {str(e)}")

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

    def initialize_graph_client_with_token(self, access_token: str) -> Optional[GraphServiceClient]:
        """Initialize the Microsoft Graph client with delegated permissions using an access token."""
        if not access_token:
            logger.error("Access token is empty when initializing Graph client")
            return None
        
        try:
            from azure.identity import TokenCredential
            from azure.core.credentials import AccessToken
            import time

            class GraphTokenCredential(TokenCredential):
                def __init__(self, token: str):
                    self.token = token

                def get_token(self, *scopes, **kwargs):
                    return AccessToken(self.token, int(time.time()) + 3600)

            credential = GraphTokenCredential(access_token)
            # Use specific scopes required for Teams chat operations
            chat_scopes = [
                "Chat.ReadWrite",
                "Chat.Create",
                "User.Read.All"
            ]
            client = GraphServiceClient(credentials=credential, scopes=chat_scopes)
            
            if client:
                logger.info("Successfully initialized Graph client with access token")
                self.graph_client = client
                return client
            else:
                logger.error("Failed to initialize Graph client with access token")
                return None
                
        except Exception as e:
            logger.error(f"Failed to initialize Graph client with access token: {str(e)}")
            return None

    async def create_or_get_chat(self, host_user_id: str, system_user_id: str, access_token: str) -> str:
        """Create or get a one-on-one Teams chat using Graph client with delegated permissions."""
        if not access_token:
            raise Exception("Access token is empty when trying to create or get chat.")

        if not self.graph_client:
            self.initialize_graph_client_with_token(access_token)

        cache_key = tuple(sorted([host_user_id, system_user_id]))
        with self._chat_id_cache_lock:
            if cache_key in self._chat_id_cache:
                return self._chat_id_cache[cache_key]

        try:
            # First try to find existing chat
            chat_id = await self.find_existing_one_on_one_chat(host_user_id, system_user_id)
            if chat_id:
                with self._chat_id_cache_lock:
                    self._chat_id_cache[cache_key] = chat_id
                return chat_id

            # If no existing chat, create a new one
            chat = {
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
            
            new_chat = await self.graph_client.chats.post(chat)
            chat_id = new_chat.id
            
            with self._chat_id_cache_lock:
                self._chat_id_cache[cache_key] = chat_id
            return chat_id

        except Exception as e:
            print(f"[ERROR] Failed to create or get chat: {str(e)}")
            raise

    async def find_existing_one_on_one_chat(self, host_user_id: str, system_user_id: str) -> str:
        """Find an existing one-on-one Teams chat using Graph client."""
        try:
            # Get all one-on-one chats
            chats = await self.graph_client.chats.get()
            
            # Filter for one-on-one chats
            one_on_one_chats = [c for c in chats.value if c.chat_type == "oneOnOne"]
            
            for chat in one_on_one_chats:
                members = await self.graph_client.chats.by_chat_id(chat.id).members.get()
                member_ids = set(m.user_id for m in members.value if m.user_id)
                if {host_user_id, system_user_id} == member_ids:
                    return chat.id
                    
            return None

        except Exception as e:
            print(f"[ERROR] Failed to find existing chat: {str(e)}")
            raise

    async def send_message_to_host(self, chat_id: str, access_token: str, message: str):
        """Send a Teams message using Graph client with delegated permissions."""
        try:
            print("[DEBUG] Starting send_message_to_host...")
            if not access_token:
                raise Exception("Access token is empty when trying to send message.")
                
            if not chat_id:
                raise Exception("Chat ID is empty when trying to send message.")
                
            if not message:
                raise Exception("Message content is empty.")

            print(f"[DEBUG] Initializing Graph client for chat {chat_id}")
            if not self.graph_client:
                self.initialize_graph_client_with_token(access_token)

            chat_message = ChatMessage(
                body={
                    "content": message,
                    "contentType": "text"
                }
            )
            
            print(f"[DEBUG] Sending message to chat {chat_id}: {message[:50]}...")
            result = await self.graph_client.chats.by_chat_id(chat_id).messages.post(chat_message)
            print(f"[DEBUG] Message sent successfully. Message ID: {result.id if result else 'Unknown'}")
            return result

        except Exception as e:
            print(f"[ERROR] Failed to send Teams message: {str(e)}")
            print(f"[DEBUG] Access token first 10 chars: {access_token[:10]}")
            print(f"[DEBUG] Chat ID: {chat_id}")
            raise

    async def send_teams_message(self, recipient_email: str, message: str, access_token: str = None) -> bool:
        """
        Send a Teams message to a specific user using delegated permissions.
        
        Args:
            recipient_email: The email address of the message recipient
            message: The message content to send
            access_token: Optional delegated access token from user session
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not access_token:
            logger.error("No access token provided for Teams message")
            return False
            
        try:
            logger.info(f"Attempting to send Teams message to {recipient_email}")
            
            try:
                # Initialize Graph client with delegated token
                self.initialize_graph_client_with_token(access_token)
                
                # Get user IDs
                recipient_id = self.get_user_id(recipient_email, access_token)
                system_id = self.get_user_id(self._system_account_email, access_token)
                
                # Get or create chat
                chat_id = await self.create_or_get_chat(recipient_id, system_id, access_token)
                
                if not chat_id:
                    logger.error("Failed to get or create chat")
                    return False
                
                # Send the message
                logger.info(f"Sending message to chat {chat_id}")
                await self.send_message_to_host(chat_id, access_token, message)
                logger.info("Message sent successfully")
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to send Teams message: {error_msg}")
                
                if "Authorization_RequestDenied" in error_msg:
                    logger.error("Authorization denied. Please verify Teams message permissions are granted")
                elif "InvalidAuthenticationToken" in error_msg:
                    logger.error("Invalid authentication token. Token may have expired")
                elif "ResourceNotFound" in error_msg:
                    logger.error(f"Could not find user: {recipient_email}")
                
                if result and result.id:
                    print(f"[INFO] Successfully sent Teams message to {recipient_email}")
                    return True
                else:
                    print("[ERROR] Failed to send Teams message - no message ID returned")
                    return False
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[ERROR] Failed to send Teams message: {error_msg}")
                
                if "Authorization_RequestDenied" in error_msg:
                    print("[ERROR] Authorization denied. Please verify Teams message permissions are granted")
                elif "InvalidAuthenticationToken" in error_msg:
                    print("[ERROR] Invalid authentication token. Token may have expired")
                elif "ResourceNotFound" in error_msg:
                    print(f"[ERROR] Could not find user: {recipient_email}")
                    # Clear cache in case the user was removed
                    with self._chat_id_cache_lock:
                        self._chat_id_cache.pop(recipient_email, None)
                
                return False
                
        except Exception as e:
            print(f"[ERROR] Unexpected error sending Teams message: {str(e)}")
            return False

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
                print("[DEBUG] Starting Teams notification process...")
                access_token = self.get_system_account_token()
                print("[DEBUG] Got access token successfully")
                
                if not access_token:
                    raise Exception("Access token is empty after acquisition!")
                    
                print(f"[DEBUG] Getting user ID for host: {host_email}")
                host_user_id = self.get_user_id(host_email, access_token)
                print(f"[DEBUG] Got host user ID: {host_user_id}")
                
                print(f"[DEBUG] Getting user ID for system account: {self._system_account_email}")
                system_user_id = self.get_user_id(self._system_account_email, access_token)
                print(f"[DEBUG] Got system user ID: {system_user_id}")
                
                print("[DEBUG] Creating/getting chat...")
                chat_id = await self.create_or_get_chat(host_user_id, system_user_id, access_token)
                print(f"[DEBUG] Got chat ID: {chat_id}")
                
                message = (
                    f"A visitor has arrived at reception to meet you: {visitor_name}. "
                    "Please check the Teams calendar for details."
                )
                
                print("[DEBUG] Sending message...")
                await self.send_message_to_host(chat_id, access_token, message)
                print(f"[DEBUG] Teams notification sent successfully to {host_email}")
                
            except Exception as e:
                print(f"[ERROR] Failed to send Teams notification: {str(e)}")
                print(f"[ERROR] Full error details: {e.__class__.__name__}: {str(e)}")
                # Don't raise the exception - we want the function to return True if meeting was created

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

"""Microsoft Graph API client for DPL Receptionist."""
from typing import Optional, List, Dict, Any
from msgraph import GraphServiceClient
from azure.identity import ClientSecretCredential
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_graph_client(tenant_id: str, client_id: str, client_secret: str) -> Optional[GraphServiceClient]:
    """Initialize Microsoft Graph client with delegated permissions."""
    try:
        # Import required modules
        import msal
        import os
        from azure.core.credentials import AccessToken
        import time

        class DelegatedTokenCredential:
            def __init__(self, tenant_id: str, client_id: str, client_secret: str):
                self.tenant_id = tenant_id
                self.client_id = client_id
                self.client_secret = client_secret
                self.app = msal.ConfidentialClientApplication(
                    client_id=client_id,
                    client_credential=client_secret,
                    authority=f"https://login.microsoftonline.com/{tenant_id}"
                )

            def get_token(self, *scopes, **kwargs):
                # Try to get token silently first
                result = self.app.acquire_token_silent(list(scopes), account=None)
                if not result:
                    # If no cached token, get new token with username/password
                    result = self.app.acquire_token_by_username_password(
                        username=os.getenv("GRAPH_USERNAME"),
                        password=os.getenv("GRAPH_PASSWORD"),
                        scopes=list(scopes)
                    )
                
                if result and 'access_token' in result:
                    return AccessToken(result['access_token'], int(time.time()) + result.get('expires_in', 3600))
                raise Exception("Failed to acquire token")

        # Create credential object with delegated auth
        credential = DelegatedTokenCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        
        # Create Graph client with chat and user scopes
        scopes = [
            "https://graph.microsoft.com/Chat.ReadWrite",
            "https://graph.microsoft.com/Chat.Create",
            "https://graph.microsoft.com/User.Read.All"
        ]
        client = GraphServiceClient(credentials=credential, scopes=scopes)
        
        logger.info("Successfully created Graph client with delegated permissions")
        return client
        
    except Exception as e:
        logger.error(f"Failed to initialize Graph client: {str(e)}")
        return None

async def search_users(client: GraphServiceClient, search_term: str) -> Optional[List[Dict[str, Any]]]:
    """Search for users in the organization using Microsoft Graph API."""
    try:
        logger.info(f"Searching users with term: {search_term}")
        
        # Build the request with proper parameters
        filter_query = f"startswith(displayName,'{search_term}') or startswith(mail,'{search_term}')"
        select = ["id", "displayName", "mail", "jobTitle", "department"]
        
        # Make the request
        response = await client.users.get()
        
        if not response or not hasattr(response, 'value'):
            logger.warning("No users found or unexpected response format")
            return None
            
        users = response.value
        logger.info(f"Successfully retrieved {len(users)} users")
        
        # Filter results on the client side since $filter isn't working
        filtered_users = [
            user for user in users 
            if search_term.lower() in (getattr(user, 'display_name', '').lower() or '') or 
               search_term.lower() in (getattr(user, 'mail', '').lower() or '')
        ]
        
        return filtered_users
        
    except Exception as e:
        logger.error(f"Failed to search users: {str(e)}")
        return None

async def get_users(client: GraphServiceClient) -> Optional[List[Dict[str, Any]]]:
    """Get all users from Microsoft Graph API."""
    try:
        logger.info("Getting all users from Graph API")
        response = await client.users.get()
        
        if not response or not hasattr(response, 'value'):
            logger.warning("No users found or unexpected response format")
            return None
            
        users = response.value
        logger.info(f"Successfully retrieved {len(users)} users")
        return users
        
    except Exception as e:
        logger.error(f"Failed to get users: {str(e)}")
        return None
            
    except Exception as e:
        print(f"[ERROR] Failed to create Graph client: {str(e)}")
        return None

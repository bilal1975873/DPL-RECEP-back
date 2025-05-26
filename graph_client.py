from typing import Optional
import json
from msgraph import GraphServiceClient
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
from azure.identity import OnBehalfOfCredential

class GraphTokenCredential(TokenCredential):
    """TokenCredential implementation for access token authentication."""
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_token(self, *scopes, **kwargs):
        """Returns the access token for the specified scope."""
        from azure.core.credentials import AccessToken
        import time
        # Create an AccessToken object with the token and an expiration time
        # We'll set expiration to 1 hour from now since we can't know the actual expiration
        return AccessToken(self.access_token, int(time.time()) + 3600)

def create_graph_client(access_token: str) -> Optional[GraphServiceClient]:
    """Create a Microsoft Graph client with application permissions using an access token."""
    try:
        # Create credential from access token
        credential = GraphTokenCredential(access_token)
        
        # Create client with application permissions
        client = GraphServiceClient(credentials=credential)
        
        # Test the client by looking up the system admin account
        try:
            print("[DEBUG] Testing Graph client connection...")
            test = client.users.get()
            if test:
                print("[DEBUG] Successfully created and tested Graph client with application permissions")
                return client
            else:
                print("[ERROR] Could not verify Graph client connection")
                return None
        except Exception as e:
            print(f"[ERROR] Graph client test failed: {str(e)}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Failed to create Graph client: {str(e)}")
        return None

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
from azure.identity import OnBehalfOfCredential, AccessTokenCredential

class GraphTokenCredential(TokenCredential):
    """TokenCredential implementation for access token authentication."""
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_token(self, *scopes, **kwargs):
        """Returns the access token for the specified scope."""
        return self.access_token

def create_graph_client(access_token: str) -> Optional[GraphServiceClient]:
    """Create a Microsoft Graph client with delegated permissions using an access token."""
    try:
        # Create credential from access token
        credential = GraphTokenCredential(access_token)
        
        # Create Graph client with delegated scopes
        scopes = [
            'Chat.ReadWrite',
            'ChatMessage.Send',
            'User.Read.All',
            'Calendars.ReadWrite'
        ]
        
        client = GraphServiceClient(credentials=credential, scopes=scopes)
        print("[DEBUG] Successfully created Graph client with delegated permissions")
        return client
            
    except Exception as e:
        print(f"[ERROR] Failed to create Graph client: {str(e)}")
        return None

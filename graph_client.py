from typing import Optional
import os
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.attendee import Attendee
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.location import Location
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody

def create_graph_client(tenant_id: str, client_id: str, client_secret: str) -> Optional[GraphServiceClient]:
    """Create a Microsoft Graph client with the given credentials."""
    try:
        # Create credential object
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        
        # Define scopes for application permissions
        scopes = ['https://graph.microsoft.com/.default']
        
        # Create Graph client with scopes
        client = GraphServiceClient(credentials=credential, scopes=scopes)
        
        # Test the client by making a simple request
        try:
            # Attempt to get /me to verify credentials work
            client.me.get()
            return client
        except Exception as e:
            print(f"Error validating Graph client: {e}")
            return None
            
    except Exception as e:
        print(f"Error creating Graph client: {e}")
        return None

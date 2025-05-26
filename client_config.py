# client_config.py
from azure.identity import ClientSecretCredential
from typing import Optional

class ClientConfig:
    """Handles Microsoft Graph API authentication with OAuth2 delegated permissions."""
    
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._scope = None

    def get_token(self, scope: Optional[str] = None):
        """Get a token with the specified scope."""
        if scope and scope != self._scope:
            self._scope = scope
            self._token = None
            
        if not self._token:
            # Create credential object
            credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            # Get token with scope
            self._token = credential.get_token(scope or "https://graph.microsoft.com/.default")
            
        return self._token.token

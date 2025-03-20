from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer

from .auth import AuthManager


class AgentAuthMiddleware(HTTPBearer):
    def __init__(self, auth_manager: AuthManager):
        super().__init__(auto_error=True)
        self.auth_manager = auth_manager

    async def __call__(self, request: Request):
        credentials = await super().__call__(request)

        instance_id = self.auth_manager.verify_agent_key(credentials.credentials)
        if not instance_id:
            raise HTTPException(status_code=403, detail="Invalid API key")

        request.state.instance_id = instance_id
        return credentials

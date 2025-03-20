from typing import List, Optional

from pydantic import BaseModel

from mltoolbox.clients.lambda_client.openapi_client import ApiClient, Configuration, DefaultApi
from mltoolbox.clients.lambda_client.openapi_client.models import TerminateInstanceRequest
from mltoolbox.clients.lambda_client.openapi_client.models.instance import Instance

from .base import Backend


class TerminateResponse(BaseModel):
    success: bool
    terminated_instances: List[str]


class RestartResponse(BaseModel):
    success: bool
    restarted_instances: List[str]


class LambdaBackend(Backend):
    def __init__(self, api_key: str):
        self.api_key = api_key
        configuration = Configuration(
            host="https://cloud.lambdalabs.com/api/v1",
            access_token=api_key,
        )
        self.client = ApiClient(configuration)
        self.api = DefaultApi(self.client)

    def get_instances(self) -> List[Instance]:
        try:
            response = self.api.list_instances()
            return response.data
        except Exception as e:
            raise RuntimeError(f"Failed to get instances: {e}")

    def get_instance_status(self, instance_id: str) -> Optional[Instance]:
        try:
            response = self.api.get_instance(instance_id)
            return response.data
        except Exception as e:
            if e.status == 404:
                return None
            raise RuntimeError(f"Failed to get instance {instance_id}: {e}")

    def stop_instance(self, instance_id: str) -> TerminateResponse:
        try:
            request = TerminateInstanceRequest(instance_ids=[instance_id])
            response = self.api.terminate_instance(request)
            return TerminateResponse(
                success=response.data.terminated_instances == [instance_id],
                terminated_instances=response.data.terminated_instances,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to terminate instance {instance_id}: {e}")

    def restart_instance(self, instance_id: str) -> RestartResponse:
        pass

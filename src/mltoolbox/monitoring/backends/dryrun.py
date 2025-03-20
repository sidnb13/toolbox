from typing import Any, Dict, List, Optional

from .base import Backend


class DryRunBackend(Backend):
    """Mock backend for dry run mode that simulates successful API responses"""

    def __init__(self, api_key: str = "dummy"):
        self.api_key = api_key

    def get_instances(self) -> List[Dict[str, Any]]:
        return [{"id": "dry-run-instance", "status": "active"}]

    def get_instance_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        return {"id": instance_id, "status": "active", "name": f"dry-run-{instance_id}"}

    def stop_instance(self, instance_id: str) -> None:
        return {"status": "success", "message": f"Instance {instance_id} stopped successfully"}

    def restart_instance(self, instance_id: str) -> None:
        return {"status": "ok", "message": f"Instance {instance_id} restarted successfully"}

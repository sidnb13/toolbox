from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum


class BackendType(Enum):
    LAMBDA_LABS = "lambda_labs"
    DRY_RUN = "dry_run"


class Backend(ABC):
    @abstractmethod
    def get_instances(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_instance_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def stop_instance(self, instance_id: str) -> None:
        pass

    @abstractmethod
    def restart_instance(self, instance_id: str) -> None:
        pass

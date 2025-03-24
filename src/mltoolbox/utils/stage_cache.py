import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

import click

from mltoolbox.utils.helpers import RemoteConfig
from mltoolbox.utils.sftp import SFTPClient

T = TypeVar("T")


def generate_lockfile_content(stage_name: str, config_dict: Dict[str, Any]) -> str:
    """Generate lockfile content with metadata about stage execution.

    Args:
        stage_name: Name of the setup stage
        config_dict: Dictionary of configuration values

    Returns:
        str: JSON content for lockfile
    """
    # Sort the dictionary to ensure consistent ordering
    config_hash = compute_config_hash(config_dict)

    lockfile_data = {
        "stage": stage_name,
        "config_hash": config_hash,
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        # Store a simplified version of config for debugging
        "config": {
            k: str(v)[:50] for k, v in config_dict.items() if k != "_stage_name"
        },
    }

    return json.dumps(lockfile_data, indent=2)


def compute_config_hash(config_dict: Dict[str, Any]) -> str:
    """Compute a hash of the configuration dictionary.

    Args:
        config_dict: Dictionary of configuration values

    Returns:
        str: Hash of the configuration
    """
    # Sort the dictionary to ensure consistent ordering
    serialized = json.dumps(config_dict, sort_keys=True)
    # Compute a hash of the serialized configuration
    return hashlib.md5(serialized.encode()).hexdigest()  # noqa: S324


def check_stage_cache(
    remote_config: RemoteConfig,
    stage_name: str,
    project_name: str,
    config_dict: Dict[str, Any],
) -> bool:
    """Check if a stage is cached with matching configuration.

    Args:
        remote_config: Remote configuration
        stage_name: Name of the setup stage
        project_name: Name of the project
        config_dict: Current configuration dictionary

    Returns:
        bool: True if stage is cached with matching configuration
    """
    lockfile_path = f"~/.config/mltoolbox/cache/{project_name}/{stage_name}.lock"

    with SFTPClient(remote_config) as client:
        if not client.file_exists(lockfile_path):
            return False

        # Read lockfile content
        try:
            lockfile_content = client.read_file(lockfile_path)
            lockfile_data = json.loads(lockfile_content)

            # Get stored hash
            stored_hash = lockfile_data.get("config_hash")
            if not stored_hash:
                return False

            # Compute current hash
            current_hash = compute_config_hash(config_dict)

            # Compare hashes
            return stored_hash == current_hash
        except (json.JSONDecodeError, KeyError):
            # Invalid lockfile
            return False


def write_stage_lockfile(
    remote_config: RemoteConfig,
    stage_name: str,
    project_name: str,
    config_dict: Dict[str, Any],
):
    """Write a lockfile for a completed stage.

    Args:
        remote_config: Remote configuration
        stage_name: Name of the setup stage
        project_name: Name of the project
        config_dict: Configuration dictionary
    """
    cache_dir = f"~/.config/mltoolbox/cache/{project_name}"
    lockfile_path = f"{cache_dir}/{stage_name}.lock"

    # Generate lockfile content
    lockfile_content = generate_lockfile_content(stage_name, config_dict)

    with SFTPClient(remote_config) as client:
        # Ensure cache directory exists
        client.ensure_dir(cache_dir)
        # Write lockfile
        client.write_file(lockfile_path, lockfile_content)


class SetupStage:
    """Decorator and manager for remote setup stages with lockfile-based caching."""

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        cache_key_func: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        """Initialize setup stage.

        Args:
            name: Name of the setup stage
            description: Human-readable description of what this stage does
            cache_key_func: Optional function to extract cache key from kwargs
        """
        self.name = name
        self.description = description or f"Running {name}"
        self.cache_key_func = cache_key_func

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap a function as a cacheable setup stage.

        Args:
            func: Function to wrap

        Returns:
            Wrapped function that implements caching logic
        """

        def wrapper(
            remote_config: RemoteConfig,
            project_name: str,
            force: bool = False,
            **kwargs,
        ) -> T:
            """Wrapped function with caching logic.

            Args:
                remote_config: Remote configuration
                project_name: Project name
                force: Force execution even if cached
                **kwargs: Additional arguments to pass to the function

            Returns:
                Result of the function
            """
            # Get configuration dictionary for cache key
            config_dict = self._prepare_config_dict(kwargs)

            # Check if cached
            cached = not force and check_stage_cache(
                remote_config, self.name, project_name, config_dict
            )

            if cached:
                # Get the hash for display
                config_hash = compute_config_hash(config_dict)
                click.echo(
                    f"📦 Skipping {self.name} (cached with hash {config_hash[:8]})"
                )
                return cast(T, True)

            # Log execution reason
            if force:
                click.echo(f"🔄 {self.description} (forced)")
            else:
                click.echo(f"🔄 {self.description} (not cached)")

            # Execute the function
            start_time = time.time()
            try:
                result = func(
                    remote_config=remote_config, project_name=project_name, **kwargs
                )

                # Mark as complete only if successful
                if result is not False:  # Consider False as explicit failure
                    write_stage_lockfile(
                        remote_config, self.name, project_name, config_dict
                    )
                    duration = time.time() - start_time
                    click.echo(f"✅ {self.name} completed in {duration:.1f}s")
                else:
                    click.echo(f"❌ {self.name} failed")

                return result
            except Exception as e:
                duration = time.time() - start_time
                click.echo(f"❌ {self.name} failed after {duration:.1f}s: {str(e)}")
                raise

        return wrapper

    def _prepare_config_dict(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare configuration dictionary for signature calculation.

        Args:
            kwargs: Keyword arguments passed to the function

        Returns:
            Dict containing values to use for cache signature
        """
        if self.cache_key_func:
            config = self.cache_key_func(kwargs)
            # Add stage name to ensure uniqueness between stages
            config["_stage_name"] = self.name
            return config

        # Default: use all kwargs that aren't callables or complex objects
        result = {"_stage_name": self.name}
        for k, v in kwargs.items():
            # Skip callables like functions
            if callable(v):
                continue

            # Convert simple types directly
            if v is None or isinstance(v, (str, int, float, bool)):
                result[k] = v
            # Handle lists/tuples of simple types
            elif isinstance(v, (list, tuple)) and all(
                isinstance(x, (str, int, float, bool)) for x in v
            ):
                result[k] = list(v)
            # Handle dicts with simple keys/values
            elif isinstance(v, dict) and all(
                isinstance(kk, (str, int))
                and isinstance(vv, (str, int, float, bool, list, tuple))
                for kk, vv in v.items()
            ):
                result[k] = v
            # Skip complex objects
            else:
                continue

        return result

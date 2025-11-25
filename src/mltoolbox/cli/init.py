import os
import re
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv

from mltoolbox.utils.logger import get_logger
from mltoolbox.utils.templates import generate_project_files


@click.command()
@click.option("--ray/--no-ray", default=True, help="Include Ray setup")
@click.option("--force", is_flag=True, help="Force overwrite existing files")
@click.option(
    "--python-version",
    default="3.12.12",
    help="Python version to use (e.g., 3.11.12)",
)
@click.option(
    "--variant",
    default="cuda",
    type=click.Choice(["cuda", "gh200"]),
    help="Base image variant to use",
)
def init(
    ray: bool,
    force: bool = False,
    python_version: str = "3.12.12",
    variant: str = "cuda",
    ssh_key_name: str = "id_ed25519",
):
    """Initialize mltoolbox in the current project directory.

    Must be run from the project root directory.
    """
    if python_version and not re.match(r"^\d+\.\d+\.\d+$", python_version):
        raise click.ClickException(
            "Please specify the full Python version, e.g., 3.11.12"
        )

    project_dir = Path.cwd()
    project_name = project_dir.name

    # Validate we're in a project root
    if not (project_dir / "pyproject.toml").exists():
        raise click.ClickException(
            f"No pyproject.toml found in {project_dir}. "
            "Please run this command from your project root directory."
        )

    # Strip to major.minor for main container build
    python_version_major_minor = ".".join(python_version.split(".")[:2])
    load_dotenv(".env")
    # Build base image if it doesn't exist
    git_name = os.getenv("GIT_NAME")
    if not git_name:
        git_name = click.prompt("Enter your GitHub username")
        os.environ["GIT_NAME"] = git_name

    git_email = os.getenv("GIT_EMAIL")
    if not git_email:
        git_email = click.prompt("Enter your GitHub email")
        os.environ["GIT_EMAIL"] = git_email

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        github_token = click.prompt("Enter your GitHub token", hide_input=True)
        os.environ["GITHUB_TOKEN"] = github_token

    # Create template env variables
    template_env = {
        "python_version": python_version,
        "git_name": git_name,
        "git_email": git_email,
        "github_token": github_token,
        "project_name": project_name,
        "wandb_project": project_name,
        "wandb_entity": git_name,  # default to git username
        "wandb_api_key": "your_wandb_api_key",
        "log_level": "DEBUG",
        "model_cache_dir": "./assets/models",
        "hf_home": "~/.cache/huggingface",
        "ray_excludes": "experiments/RAVEL/data/**/*.arrow,data/**/*.arrow,*.arrow",
        "ssh_key_name": ssh_key_name,
    }

    # Generate project files
    project_dir.mkdir(exist_ok=True)
    generate_project_files(
        project_dir,
        project_name=project_name,
        ray=ray,
        env_vars=template_env,
        python_version=python_version_major_minor,  # Use major.minor for main container
        variant=variant,
    )

    logger = get_logger()
    logger.success(f"Project {project_name} (re)initialized!")
    logger.info(f"Using {variant} base image")

    # Display next steps in compact tree format
    now = datetime.now().strftime("%H:%M:%S")
    logger.console.print(f"{now}  [bold blue]●[/bold blue]  [bold]Next steps[/bold]")
    logger.console.print(
        "      ├─ [dim]Edit pyproject.toml to add your project-specific dependencies[/dim]"
    )
    logger.console.print(
        "      ├─ [dim]Run 'uv sync --locked' to install dependencies[/dim]"
    )
    logger.console.print(
        "      └─ [dim]Run 'mltoolbox container start' to begin development[/dim]"
    )

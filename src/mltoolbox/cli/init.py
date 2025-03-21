import os
from pathlib import Path

import click
from dotenv import load_dotenv

from mltoolbox.utils.templates import generate_project_files


@click.command()
@click.argument("project_name")
@click.option("--ray/--no-ray", default=True, help="Include Ray setup")
@click.option("--force", is_flag=True, help="Force overwrite existing files")
@click.option(
    "--inside-project",
    is_flag=True,
    help="Initialize inside existing project",
)
@click.option(
    "--python-version",
    default="3.12",
    type=click.Choice(["3.10", "3.11", "3.12"]),
    help="Python version to use",
)
@click.option(
    "--variant",
    default="cuda",
    type=click.Choice(["cuda", "gh200"]),
    help="System variant to use",
)
@click.option(
    "--env-variant",
    default="default",
    help="Environment variant to use (e.g., a10, a100)",
)
@click.option(
    "--ssh-key-name",
    default="id_ed25519",
    help="SSH key name to use (e.g., 'github', 'id_ed25519')",
)
def init(
    project_name: str,
    ray: bool,
    force: bool = False,
    inside_project: bool = False,
    python_version: str = "3.12",
    variant: str = "cuda",
    env_variant: str = "default",
    ssh_key_name: str = "id_ed25519",
):
    """Initialize a new ML project."""
    load_dotenv(".env")
    project_dir = Path(project_name) if not inside_project else Path.cwd()
    project_name = project_dir.name

    if (
        not force
        and any(project_dir.iterdir())
        and not click.confirm(
            f"Directory {project_name} exists. Continue?",
            default=True,
        )
    ):
        return
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
        python_version=python_version,
        variant=variant,
        env_variant=env_variant,
    )

    click.echo(f"✨ Project {project_name} (re)initialized!")
    click.echo(f"🧩 System variant: {variant}, Environment variant: {env_variant}")
    click.echo("\nNext steps:")
    click.echo("1. Add your requirements to requirements.txt")
    click.echo("2. Run 'mltoolbox container start' to begin development")

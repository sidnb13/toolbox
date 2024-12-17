import os
import subprocess
from pathlib import Path

import click

from ..utils.docker import build_base_image
from ..utils.templates import generate_project_files


@click.command()
@click.option("--cuda-version", default="12.1.0", help="CUDA version for base image")
@click.option("--python-version", default="3.12", help="Python version")
@click.option("--push", is_flag=True, default=True, help="Push image after building")
def init_base(cuda_version: str, python_version: str, push: bool):
    """Build the base image"""
    build_base_image(cuda_version, python_version, push)


@click.command()
@click.argument("project_name")
@click.option("--ray/--no-ray", default=True, help="Include Ray setup")
@click.option("--cuda-version", default="12.1.0", help="CUDA version for base image")
@click.option("--python-version", default="3.12", help="Python version")
@click.option("--force", is_flag=True, help="Force overwrite existing files")
@click.option(
    "--inside-project", is_flag=True, help="Initialize inside existing project"
)
def init(
    project_name: str,
    ray: bool,
    cuda_version: str,
    python_version: str,
    force: bool,
    inside_project: bool,
):
    """Initialize a new ML project"""
    project_dir = Path(project_name) if not inside_project else Path.cwd()
    project_name = project_dir.name

    if not force and any(project_dir.iterdir()):
        if not click.confirm(
            f"Directory {project_name} exists. Continue?", default=True
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

    # Check if base image exists
    result = subprocess.run(
        ["docker", "images", "-q", f"ghcr.io/{git_name}/ml-base:latest"],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        if click.confirm("Base image not found. Build it now?", default=True):
            build_base_image(cuda_version, python_version, push=True)

    # Create template env variables
    template_env = {
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
    }

    # Generate project files
    project_dir.mkdir(exist_ok=True)
    generate_project_files(
        project_dir,
        project_name=project_name,
        ray=ray,
        env_vars=template_env,
    )

    click.echo(f"✨ Project {project_name} initialized!")
    click.echo("\nNext steps:")
    click.echo("1. Add your requirements to requirements.txt")
    click.echo("2. Run 'mltoolbox container start' to begin development")

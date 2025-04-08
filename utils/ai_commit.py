"""
AI Commit Message Generator

A Git hook that uses OpenAI to generate commit messages based on your changes.
"""

import os
import subprocess
import sys

import openai
from dotenv import load_dotenv

load_dotenv()


def get_git_diff():
    """Get the staged git diff."""
    try:
        # Get diff of staged changes
        diff = subprocess.check_output(
            ["git", "diff", "--cached", "--no-color"],
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        return diff
    except subprocess.CalledProcessError as e:
        print(f"Error getting git diff: {e}")
        sys.exit(1)


def generate_commit_message(diff_text):
    """Generate a commit message using OpenAI."""
    # Set up OpenAI client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables")
        print("Add it to your .env file or set it as an environment variable")
        return None

    client = openai.OpenAI(api_key=api_key)

    # Prompt for OpenAI
    prompt = f"""
    Based on the following git diff, generate a concise commit message (20 words or less) 
    following a convention format like "[type] brief description". 
    
    Types can include: [feat], [fix], [docs], [style], [refactor], [test], [chore], etc.
    
    Make it descriptive but brief. Just return the commit message, nothing else.
    
    Git diff:
    {diff_text[:4000]}  # Limit diff size
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.7,
        )

        message = response.choices[0].message.content.strip()

        # Clean up the message if needed
        if message.startswith('"') and message.endswith('"'):
            message = message[1:-1]

        return message
    except Exception as e:
        print(f"Error generating commit message: {e}")
        return None


def main():
    """Main function for the prepare-commit-msg hook."""
    # When running as a git hook, we'll have arguments
    if len(sys.argv) >= 2:
        commit_msg_file = sys.argv[1]

        # Get the current commit message
        with open(commit_msg_file) as f:
            current_msg = f.read().strip()

        # Skip if message is already provided or this is a merge commit
        if current_msg and not current_msg.startswith("#"):
            return

        diff = get_git_diff()

        if not diff.strip():
            print("No changes detected in staged files.")
            return

        commit_message = generate_commit_message(diff)

        if commit_message:
            # Save the generated message
            with open(commit_msg_file, "w") as f:
                f.write(commit_message + "\n\n")
                # Preserve the comments
                if current_msg:
                    f.write(current_msg)

            print(f"Generated commit message: {commit_message}")
    else:
        # When run directly without arguments, show help
        print("AI Commit Message Generator")
        print("This script should be installed as a git hook.")
        print("Use the installer script to set it up.")


if __name__ == "__main__":
    main()

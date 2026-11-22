"""Add a person who can sign in to CogniPM (or reset what a script can: this only ever adds).

Run from backend/ with the same DATABASE_URL the API uses:

    python scripts/create_user.py pat@example.com --name "Pat Example" --role pm

It asks for the password, so it never appears in your shell history. Roles: pm (can change things) or developer
(can only look). A PM can also add people from the API (POST /api/users) once someone has signed in.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from cognipm.auth import create_user
from cognipm.db.connection import get_connection


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("email")
    parser.add_argument("--name", required=True, help="how they are shown, for example in the activity log")
    parser.add_argument("--role", choices=["pm", "developer"], default="developer")
    args = parser.parse_args()

    password = getpass.getpass("Password (at least 10 characters): ")
    if getpass.getpass("Again: ") != password:
        print("The two passwords are different. Nothing was created.")
        return 1
    try:
        user = create_user(
            get_connection(), email=args.email, display_name=args.name, role=args.role, password=password
        )
    except ValueError as problem:
        print(problem)
        return 1
    print(f"Created {user.display_name} ({user.email}) as {user.role}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

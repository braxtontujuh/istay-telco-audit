"""Operator-only local administration. No default credentials, no password in argv."""

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import Login
from app.db import engine
from app.models import Site, Telco, User
from app.security import hasher


def seed(db):
    for code in ("IP1", "IP2", "SAC", "SILC"):
        if not db.scalar(select(Site).where(Site.code == code)):
            db.add(Site(code=code, name=code))
    for name in ("CelcomDigi", "Maxis", "U Mobile", "Yes 5G", "Unifi Mobile", "Other"):
        if not db.scalar(select(Telco).where(Telco.name == name)):
            db.add(Telco(name=name))
    db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "create-admin"])
    args = parser.parse_args()
    with Session(engine()) as db:
        if args.command == "seed":
            seed(db)
            print("Sites and telcos seeded (idempotent). No users created.")
            return
        username = input("Admin username (lowercase, at least 3 characters): ").strip()
        full_name = input("Full name: ").strip()
        password = getpass.getpass("New password (at least 14 characters): ")
        if len(password) < 14 or password != getpass.getpass("Confirm password: "):
            raise SystemExit("Password too short or confirmation mismatch")
        Login(username=username, password=password)
        if not full_name or len(full_name) > 200:
            raise SystemExit("A full name of at most 200 characters is required")
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("Username already exists; no changes made")
        db.add(
            User(username=username, full_name=full_name, password_hash=hasher.hash(password), role="ADMIN")
        )
        db.commit()
        print("Administrator created. Keep credentials in your password manager.")


if __name__ == "__main__":
    main()

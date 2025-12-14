#!/usr/bin/env python3
"""
Sync example for Moy Nalog API client.

Usage:
    export NALOG_USERNAME=your_inn
    export NALOG_PASSWORD=your_password
    python examples/sync_example.py
"""

import os
from decimal import Decimal

from moy_nalog import CancelReason, MoyNalogClientSync


def main():
    username = os.getenv("NALOG_USERNAME")
    password = os.getenv("NALOG_PASSWORD")

    if not username or not password:
        print("Set NALOG_USERNAME and NALOG_PASSWORD environment variables")
        return

    with MoyNalogClientSync() as client:
        # Authenticate
        print(f"Authenticating as {username[:4]}***...")
        profile = client.auth_by_password(username, password)
        print(f"Logged in as: {profile.full_name}")

        # Create receipt
        print("\nCreating test receipt...")
        receipt = client.create_receipt(
            name="Test service (sync)",
            amount=Decimal("1.00")
        )
        print(f"Created: {receipt.uuid}")
        print(f"URL: {receipt.print_url}")

        # Cancel it
        print("\nCanceling...")
        client.cancel_receipt(receipt.uuid, reason=CancelReason.MISTAKE)
        print("Cancelled!")


if __name__ == "__main__":
    main()

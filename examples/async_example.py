#!/usr/bin/env python3
"""
Async example for Moy Nalog API client.

Usage:
    export NALOG_USERNAME=your_inn
    export NALOG_PASSWORD=your_password
    python examples/async_example.py
"""

import asyncio
import os
from decimal import Decimal

from moy_nalog import (
    AuthenticationError,
    CancelReason,
    Client,
    IncomeType,
    MoyNalogClient,
    ServiceItem,
)


async def main():
    username = os.getenv("NALOG_USERNAME")
    password = os.getenv("NALOG_PASSWORD")

    if not username or not password:
        print("Set NALOG_USERNAME and NALOG_PASSWORD environment variables")
        return

    async with MoyNalogClient(
        session_file="session.json",  # Enable session persistence
        max_retries=3,
    ) as client:

        # Authenticate if not already
        if not client.is_authenticated:
            print(f"Authenticating as {username[:4]}***...")
            try:
                profile = await client.auth_by_password(username, password)
                print(f"Logged in as: {profile.full_name} (INN: {profile.inn})")
            except AuthenticationError as e:
                print(f"Auth failed: {e}")
                return
        else:
            print(f"Session restored, INN: {client.inn}")

        # Get user profile
        profile = await client.get_user_profile()
        print(f"\nProfile: {profile.display_name}")
        print(f"Status: {profile.status}")

        # Create simple receipt
        print("\n--- Creating simple receipt (1 RUB) ---")
        receipt = await client.create_receipt(
            name="Test service",
            amount=Decimal("1.00")
        )
        print(f"Created: {receipt.uuid}")
        print(f"URL: {receipt.print_url}")

        # Create multi-item receipt
        print("\n--- Creating multi-item receipt ---")
        items = [
            ServiceItem(name="Service A", amount=Decimal("1.50"), quantity=2),
            ServiceItem(name="Service B", amount=Decimal("0.50"), quantity=1),
        ]
        receipt2 = await client.create_receipt_multi(items)
        print(f"Created: {receipt2.uuid}")
        print(f"Total: {receipt2.total_amount} RUB")

        # Create receipt with client info
        print("\n--- Creating receipt with client ---")
        client_info = Client(
            income_type=IncomeType.INDIVIDUAL,
            display_name="Test Customer",
        )
        receipt3 = await client.create_receipt(
            name="Service with client",
            amount=Decimal("1.00"),
            client=client_info,
        )
        print(f"Created: {receipt3.uuid}")

        # Get income list
        print("\n--- Recent incomes ---")
        incomes = await client.get_incomes(limit=5)
        for income in incomes.items[:5]:
            status = "CANCELLED" if income.is_cancelled else "ACTIVE"
            print(f"  {income.uuid[:8]}... | {income.total_amount} RUB | {status}")

        # Cancel test receipts
        print("\n--- Canceling test receipts ---")
        for r in [receipt, receipt2, receipt3]:
            cancelled = await client.cancel_receipt(r.uuid, reason=CancelReason.MISTAKE)
            print(f"Cancelled: {cancelled.uuid}")

        print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())

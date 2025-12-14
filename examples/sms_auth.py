#!/usr/bin/env python3
"""
SMS authentication example.

Usage:
    python examples/sms_auth.py
"""

import asyncio
from decimal import Decimal

from moy_nalog import CancelReason, MoyNalogClient, SMSError


async def main():
    async with MoyNalogClient() as client:
        # Get phone number
        phone = input("Enter phone (79001234567): ").strip()
        if not phone:
            print("Phone required")
            return

        # Request SMS
        print(f"Sending SMS to {phone}...")
        try:
            challenge = await client.request_sms_code(phone)
            print(f"SMS sent! Code valid for {challenge.expire_in} seconds")
        except SMSError as e:
            print(f"Error: {e}")
            return

        # Get code
        code = input("Enter code from SMS: ").strip()
        if not code:
            print("Code required")
            return

        # Verify
        print("Verifying...")
        try:
            profile = await client.auth_by_sms(phone, challenge.challenge_token, code)
            print(f"Success! INN: {profile.inn}")
        except SMSError as e:
            print(f"Error: {e}")
            return

        # Create test receipt
        print("\nCreating test receipt...")
        receipt = await client.create_receipt("SMS auth test", Decimal("1.00"))
        print(f"Created: {receipt.print_url}")

        # Cancel
        await client.cancel_receipt(receipt.uuid, CancelReason.MISTAKE)
        print("Test receipt cancelled")


if __name__ == "__main__":
    asyncio.run(main())

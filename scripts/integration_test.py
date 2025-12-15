#!/usr/bin/env python3
"""
Interactive integration test for Moy Nalog API client.

This script tests all major functionality:
- Password and SMS authentication
- Creating various types of receipts
- Downloading receipt files (PDF/JSON)
- Querying income list
- Canceling receipts
- Session persistence

All created receipts are cancelled at the end.
A detailed log file is generated.

Usage:
    python scripts/integration_test.py
"""

import asyncio
import getpass
import json
import logging
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from moy_nalog import (
    AuthenticationError,
    CancelReason,
    Client,
    IncomeType,
    MoyNalogClient,
    PaymentType,
    ReceiptError,
    ServiceItem,
    SMSError,
)


class IntegrationTest:
    """Interactive integration test runner."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.receipts_dir = output_dir / "receipts"
        self.receipts_dir.mkdir(exist_ok=True)

        self.log_file = output_dir / f"test_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.created_receipts: list[str] = []
        self.test_results: list[dict] = []

        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging to file and console."""
        self.logger = logging.getLogger("integration_test")
        self.logger.setLevel(logging.DEBUG)

        # File handler - detailed
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)

        # Console handler - info only
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def log_test(self, name: str, success: bool, details: str = "") -> None:
        """Log test result."""
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        })

        if success:
            self.logger.info(f"[PASS] {name}")
        else:
            self.logger.error(f"[FAIL] {name}: {details}")

        if details and success:
            self.logger.debug(f"       Details: {details}")

    async def download_receipt(self, client: MoyNalogClient, receipt_uuid: str) -> bool:
        """Download receipt in PDF and JSON formats."""
        self.logger.debug(f"Downloading receipt {receipt_uuid}...")

        try:
            http_client = await client._get_client()
            headers = client._get_headers(with_auth=True)

            # Download JSON
            json_url = f"{client.API_URL_V1}/receipt/{client.inn}/{receipt_uuid}/json"
            json_response = await http_client.get(json_url, headers=headers)

            if json_response.status_code == 200:
                json_path = self.receipts_dir / f"{receipt_uuid}.json"
                json_path.write_text(json_response.text, encoding="utf-8")
                self.logger.debug(f"Saved JSON: {json_path}")

            # Download printable version (HTML/PDF)
            print_url = f"{client.API_URL_V1}/receipt/{client.inn}/{receipt_uuid}/print"
            print_response = await http_client.get(print_url, headers=headers, follow_redirects=True)

            if print_response.status_code == 200:
                # Determine extension based on content type
                content_type = print_response.headers.get("content-type", "")
                if "pdf" in content_type:
                    ext = "pdf"
                elif "html" in content_type:
                    ext = "html"
                else:
                    ext = "bin"

                print_path = self.receipts_dir / f"{receipt_uuid}.{ext}"
                print_path.write_bytes(print_response.content)
                self.logger.debug(f"Saved printable: {print_path}")

            return True

        except Exception as e:
            self.logger.warning(f"Failed to download receipt {receipt_uuid}: {e}")
            return False

    async def test_authentication(self, client: MoyNalogClient, username: str, password: str) -> bool:
        """Test password authentication."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST: Password Authentication")
        self.logger.info("=" * 60)

        try:
            profile = await client.auth_by_password(username, password)

            self.log_test(
                "Password authentication",
                True,
                f"INN: {profile.inn}, Name: {profile.full_name}"
            )

            self.logger.info(f"  INN: {profile.inn}")
            self.logger.info(f"  Name: {profile.full_name}")
            self.logger.info(f"  Status: {profile.status}")

            return True

        except AuthenticationError as e:
            self.log_test("Password authentication", False, str(e))
            return False

    async def test_sms_authentication(self, client: MoyNalogClient, phone: str) -> bool:
        """Test SMS authentication (interactive)."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST: SMS Authentication")
        self.logger.info("=" * 60)

        try:
            # Step 1: Request SMS code
            self.logger.info(f"Requesting SMS code for {phone}...")
            challenge = await client.request_sms_code(phone)

            self.log_test(
                "SMS code request",
                True,
                f"Code valid for {challenge.expire_in} seconds"
            )

            self.logger.info(f"  SMS sent! Code expires in {challenge.expire_in} seconds")

            # Step 2: Get code from user
            print("\n" + "-" * 40)
            code = input("Enter SMS code: ").strip()

            if not code:
                self.log_test("SMS authentication", False, "No code entered")
                return False

            # Step 3: Verify code
            self.logger.info("Verifying SMS code...")
            profile = await client.auth_by_sms(phone, challenge.challenge_token, code)

            self.log_test(
                "SMS authentication",
                True,
                f"INN: {profile.inn}, Name: {profile.full_name}"
            )

            self.logger.info(f"  INN: {profile.inn}")
            self.logger.info(f"  Name: {profile.full_name}")
            self.logger.info(f"  Status: {profile.status}")

            return True

        except SMSError as e:
            details = str(e)
            if e.response:
                details += f" | Response: {e.response}"
            self.log_test("SMS authentication", False, details)
            return False
        except AuthenticationError as e:
            self.log_test("SMS authentication", False, str(e))
            return False

    async def test_user_profile(self, client: MoyNalogClient) -> bool:
        """Test getting user profile."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Get User Profile")

        try:
            profile = await client.get_user_profile()

            self.log_test(
                "Get user profile",
                True,
                f"Phone: {profile.phone}, Email: {profile.email}"
            )

            self.logger.debug(f"  Full profile data: {profile.model_dump()}")
            return True

        except Exception as e:
            self.log_test("Get user profile", False, str(e))
            return False

    async def test_simple_receipt(self, client: MoyNalogClient) -> bool:
        """Test creating a simple receipt."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Simple Receipt (1 item, cash)")

        try:
            receipt = await client.create_receipt(
                name="Integration test - simple receipt",
                amount=Decimal("1.00"),
            )

            self.created_receipts.append(receipt.uuid)
            await self.download_receipt(client, receipt.uuid)

            self.log_test(
                "Simple receipt creation",
                True,
                f"UUID: {receipt.uuid}, Amount: {receipt.total_amount}"
            )

            self.logger.info(f"  UUID: {receipt.uuid}")
            self.logger.info(f"  Print URL: {receipt.print_url}")

            return True

        except ReceiptError as e:
            self.log_test("Simple receipt creation", False, str(e))
            return False

    async def test_multi_item_receipt(self, client: MoyNalogClient) -> bool:
        """Test creating a receipt with multiple items."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Multi-item Receipt (3 items)")

        try:
            items = [
                ServiceItem(name="Service A - consulting", amount=Decimal("1.50"), quantity=2),
                ServiceItem(name="Service B - development", amount=Decimal("2.00"), quantity=1),
                ServiceItem(name="Service C - support", amount=Decimal("0.50"), quantity=3),
            ]

            receipt = await client.create_receipt_multi(items)

            self.created_receipts.append(receipt.uuid)
            await self.download_receipt(client, receipt.uuid)

            expected_total = Decimal("1.50") * 2 + Decimal("2.00") + Decimal("0.50") * 3

            self.log_test(
                "Multi-item receipt creation",
                receipt.total_amount == expected_total,
                f"UUID: {receipt.uuid}, Total: {receipt.total_amount} (expected: {expected_total})"
            )

            self.logger.info(f"  UUID: {receipt.uuid}")
            self.logger.info(f"  Total: {receipt.total_amount} RUB")
            self.logger.info(f"  Items: {len(items)}")

            return True

        except ReceiptError as e:
            self.log_test("Multi-item receipt creation", False, str(e))
            return False

    async def test_receipt_with_individual_client(self, client: MoyNalogClient) -> bool:
        """Test receipt with individual client info."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Receipt with Individual Client")

        try:
            client_info = Client(
                income_type=IncomeType.INDIVIDUAL,
                display_name="Test Individual Client",
                contact_phone="+79001234567",
            )

            receipt = await client.create_receipt(
                name="Service for individual",
                amount=Decimal("1.00"),
                client=client_info,
            )

            self.created_receipts.append(receipt.uuid)
            await self.download_receipt(client, receipt.uuid)

            self.log_test(
                "Receipt with individual client",
                True,
                f"UUID: {receipt.uuid}, Client: {client_info.display_name}"
            )

            self.logger.info(f"  UUID: {receipt.uuid}")
            self.logger.info("  Client type: INDIVIDUAL")

            return True

        except ReceiptError as e:
            self.log_test("Receipt with individual client", False, str(e))
            return False

    async def test_receipt_with_legal_entity(self, client: MoyNalogClient) -> bool:
        """Test receipt with legal entity client info."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Receipt with Legal Entity Client")

        try:
            client_info = Client(
                income_type=IncomeType.LEGAL_ENTITY,
                display_name="OOO Test Company",
                inn="7707083893",  # Sberbank INN for testing
            )

            receipt = await client.create_receipt(
                name="Service for legal entity",
                amount=Decimal("1.00"),
                client=client_info,
            )

            self.created_receipts.append(receipt.uuid)
            await self.download_receipt(client, receipt.uuid)

            self.log_test(
                "Receipt with legal entity client",
                True,
                f"UUID: {receipt.uuid}, Client INN: {client_info.inn}"
            )

            self.logger.info(f"  UUID: {receipt.uuid}")
            self.logger.info("  Client type: LEGAL_ENTITY")
            self.logger.info(f"  Client INN: {client_info.inn}")

            return True

        except ReceiptError as e:
            self.log_test("Receipt with legal entity client", False, str(e))
            return False

    async def test_receipt_bank_transfer(self, client: MoyNalogClient) -> bool:
        """Test receipt with bank transfer payment type (requires legal entity client)."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Receipt with Bank Transfer")

        try:
            # Bank transfer requires a legal entity client
            client_info = Client(
                income_type=IncomeType.LEGAL_ENTITY,
                display_name="OOO Bank Transfer Test",
                inn="7707083893",
            )

            receipt = await client.create_receipt(
                name="Service paid by bank transfer",
                amount=Decimal("1.00"),
                client=client_info,
                payment_type=PaymentType.WIRE,
            )

            self.created_receipts.append(receipt.uuid)
            await self.download_receipt(client, receipt.uuid)

            self.log_test(
                "Receipt with bank transfer",
                True,
                f"UUID: {receipt.uuid}, Payment: WIRE, Client: {client_info.inn}"
            )

            self.logger.info(f"  UUID: {receipt.uuid}")
            self.logger.info("  Payment type: WIRE (bank transfer)")
            self.logger.info(f"  Client INN: {client_info.inn}")

            return True

        except ReceiptError as e:
            details = str(e)
            if e.response:
                details += f" | Response: {e.response}"
            self.log_test("Receipt with bank transfer", False, details)
            return False

    async def test_get_incomes(self, client: MoyNalogClient) -> bool:
        """Test getting income list."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Get Income List")

        try:
            incomes = await client.get_incomes(limit=10)

            self.log_test(
                "Get income list",
                True,
                f"Retrieved: {len(incomes.items)}, Has more: {incomes.has_more}"
            )

            self.logger.info(f"  Items retrieved: {len(incomes.items)}")
            self.logger.info(f"  Has more: {incomes.has_more}")

            if incomes.items:
                self.logger.debug("  Recent incomes:")
                for income in incomes.items[:5]:
                    status = "CANCELLED" if income.is_cancelled else "ACTIVE"
                    self.logger.debug(f"    {income.uuid[:12]}... | {income.total_amount} RUB | {status}")

            return True

        except Exception as e:
            self.log_test("Get income list", False, str(e))
            return False

    async def test_get_receipt_data(self, client: MoyNalogClient) -> bool:
        """Test getting receipt data by UUID."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Get Receipt Data")

        if not self.created_receipts:
            self.log_test("Get receipt data", False, "No receipts created")
            return False

        try:
            receipt_uuid = self.created_receipts[0]
            data = await client.get_receipt(receipt_uuid)

            success = data is not None
            self.log_test(
                "Get receipt data",
                success,
                f"UUID: {receipt_uuid}, Data keys: {list(data.keys()) if data else 'None'}"
            )

            if data:
                self.logger.debug(f"  Receipt data: {json.dumps(data, indent=2, ensure_ascii=False, default=str)}")

            return success

        except Exception as e:
            self.log_test("Get receipt data", False, str(e))
            return False

    async def test_cancel_receipts(self, client: MoyNalogClient) -> bool:
        """Cancel all created test receipts."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("CLEANUP: Canceling All Test Receipts")
        self.logger.info("=" * 60)

        if not self.created_receipts:
            self.logger.info("No receipts to cancel")
            return True

        all_cancelled = True

        for receipt_uuid in self.created_receipts:
            try:
                await client.cancel_receipt(
                    receipt_uuid,
                    reason=CancelReason.MISTAKE,
                )

                self.log_test(
                    f"Cancel receipt {receipt_uuid[:12]}...",
                    True,
                    "Reason: MISTAKE"
                )

            except ReceiptError as e:
                self.log_test(
                    f"Cancel receipt {receipt_uuid[:12]}...",
                    False,
                    str(e)
                )
                all_cancelled = False

        self.logger.info(f"\nCancelled {len(self.created_receipts)} receipts")
        return all_cancelled

    async def test_session_persistence(
        self,
        username: str,
        password: str,
        proxy: str | None = None,
        verify_ssl: bool = True,
    ) -> bool:
        """Test session save/restore functionality."""
        self.logger.info("\n" + "-" * 40)
        self.logger.info("TEST: Session Persistence")

        session_file = self.output_dir / "test_session.json"

        try:
            # First client - authenticate and save session
            async with MoyNalogClient(
                session_file=str(session_file), proxy=proxy, verify_ssl=verify_ssl
            ) as client1:
                await client1.auth_by_password(username, password)
                inn1 = client1.inn

            # Check session file exists
            if not session_file.exists():
                self.log_test("Session persistence", False, "Session file not created")
                return False

            # Second client - should restore session
            async with MoyNalogClient(
                session_file=str(session_file), proxy=proxy, verify_ssl=verify_ssl
            ) as client2:
                inn2 = client2.inn
                is_auth = client2.is_authenticated

            success = is_auth and inn1 == inn2
            self.log_test(
                "Session persistence",
                success,
                f"Restored INN: {inn2}, Authenticated: {is_auth}"
            )

            # Cleanup
            session_file.unlink(missing_ok=True)

            return success

        except Exception as e:
            self.log_test("Session persistence", False, str(e))
            session_file.unlink(missing_ok=True)
            return False

    def generate_report(self) -> None:
        """Generate final test report."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST REPORT")
        self.logger.info("=" * 60)

        passed = sum(1 for t in self.test_results if t["success"])
        failed = sum(1 for t in self.test_results if not t["success"])
        total = len(self.test_results)

        self.logger.info(f"\nTotal tests: {total}")
        self.logger.info(f"Passed: {passed}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Success rate: {passed/total*100:.1f}%" if total > 0 else "N/A")

        if failed > 0:
            self.logger.info("\nFailed tests:")
            for test in self.test_results:
                if not test["success"]:
                    self.logger.info(f"  - {test['name']}: {test['details']}")

        self.logger.info(f"\nReceipts directory: {self.receipts_dir}")
        self.logger.info(f"Log file: {self.log_file}")

        # Save JSON report
        report_file = self.output_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "success_rate": passed/total if total > 0 else 0,
            },
            "tests": self.test_results,
            "created_receipts": self.created_receipts,
        }
        report_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.logger.info(f"JSON report: {report_file}")

    async def run(
        self,
        auth_method: str,
        username: str | None = None,
        password: str | None = None,
        phone: str | None = None,
        proxy: str | None = None,
        verify_ssl: bool = True,
        test_mode: str = "auth_only",
    ) -> bool:
        """Run integration tests.

        Args:
            auth_method: "password" or "sms"
            username: INN or phone for password auth
            password: Password for password auth
            phone: Phone number for SMS auth
            proxy: Proxy URL (optional)
            verify_ssl: Verify SSL certificates (default: True)
            test_mode: "auth_only" or "full"
        """
        self.logger.info("=" * 60)
        self.logger.info("MOY NALOG API - INTEGRATION TEST")
        self.logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Test mode: {test_mode.upper()}")
        self.logger.info(f"Auth method: {auth_method.upper()}")
        if proxy:
            # Hide password in proxy URL for logging
            import re
            safe_proxy = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', proxy)
            self.logger.info(f"Proxy: {safe_proxy}")
            self.logger.info(f"SSL verify: {verify_ssl}")
        self.logger.info("=" * 60)

        async with MoyNalogClient(proxy=proxy, verify_ssl=verify_ssl) as client:
            # Authentication
            auth_success = False
            if auth_method == "password":
                auth_success = await self.test_authentication(client, username, password)
            elif auth_method == "sms":
                auth_success = await self.test_sms_authentication(client, phone)

            if not auth_success:
                self.logger.error("Authentication failed, cannot continue")
                self.generate_report()
                return False

            # User profile
            await self.test_user_profile(client)

            # Full test mode: receipts
            if test_mode == "full":
                # Receipt creation tests
                await self.test_simple_receipt(client)
                await self.test_multi_item_receipt(client)
                await self.test_receipt_with_individual_client(client)
                await self.test_receipt_with_legal_entity(client)
                await self.test_receipt_bank_transfer(client)

                # Query tests
                await self.test_get_incomes(client)
                await self.test_get_receipt_data(client)

                # Cleanup - cancel all test receipts
                await self.test_cancel_receipts(client)
            else:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("Skipping receipt tests (auth_only mode)")

        # Session persistence test (only for password auth)
        if auth_method == "password":
            await self.test_session_persistence(username, password, proxy, verify_ssl)

        # Generate report
        self.generate_report()

        # Return overall success
        return all(t["success"] for t in self.test_results)


def get_proxy_choice() -> tuple[str | None, bool]:
    """Ask user if they want to use a proxy.

    Returns:
        Tuple of (proxy_url, verify_ssl)
    """
    print("\n" + "-" * 40)
    print("Proxy Configuration")
    print("-" * 40)

    while True:
        choice = input("Use proxy server? (y/n): ").strip().lower()
        if choice in ("y", "yes"):
            while True:
                print("\nSupported proxy formats:")
                print("  HTTP:   http://host:port")
                print("  HTTPS:  https://host:port")
                print("  SOCKS5: socks5://host:port")
                print("  SOCKS4: socks4://host:port")
                print("\nWith authentication:")
                print("  http://user:password@host:port")
                print("  socks5://user:password@host:port")
                print("\nNote: SOCKS support requires: pip install moy-nalog-api[socks]")
                print("-" * 40)

                proxy_url = input("Proxy URL (or empty to skip): ").strip()

                if not proxy_url:
                    print("Continuing without proxy.")
                    return None, True

                # Basic validation
                valid_prefixes = ("http://", "https://", "socks4://", "socks5://")
                if not proxy_url.lower().startswith(valid_prefixes):
                    print(f"\nWarning: Proxy URL should start with one of: {', '.join(valid_prefixes)}")
                    print("  1. Try again")
                    print("  2. Use this URL anyway")
                    print("  3. Continue without proxy")

                    while True:
                        retry_choice = input("Enter 1, 2, or 3: ").strip()
                        if retry_choice == "1":
                            break  # Re-enter proxy URL
                        elif retry_choice == "2":
                            # Ask about SSL verification
                            verify_ssl = get_ssl_verify_choice()
                            return proxy_url, verify_ssl
                        elif retry_choice == "3":
                            print("Continuing without proxy.")
                            return None, True
                        else:
                            print("Invalid choice. Please enter 1, 2, or 3.")
                    continue  # Go back to proxy URL input

                # Ask about SSL verification
                verify_ssl = get_ssl_verify_choice()
                return proxy_url, verify_ssl

        elif choice in ("n", "no", ""):
            return None, True
        else:
            print("Please enter 'y' or 'n'.")


def get_ssl_verify_choice() -> bool:
    """Ask user if they want to verify SSL certificates."""
    print("\n" + "-" * 40)
    print("Some proxy servers intercept SSL traffic and may cause")
    print("certificate verification errors.")
    print("-" * 40)

    while True:
        choice = input("Verify SSL certificates? (y/n) [default: y]: ").strip().lower()
        if choice in ("y", "yes", ""):
            return True
        elif choice in ("n", "no"):
            print("Warning: SSL verification disabled. Connection may be insecure.")
            return False
        else:
            print("Please enter 'y' or 'n'.")


def get_test_mode() -> str:
    """Ask user which test mode to run."""
    print("\n" + "-" * 40)
    print("Test Mode")
    print("-" * 40)
    print("  1. Auth only - test authentication and profile")
    print("  2. Full test - auth + create/cancel receipts")
    print("-" * 40)

    while True:
        choice = input("Enter 1 or 2 [default: 1]: ").strip()
        if choice == "" or choice == "1":
            return "auth_only"
        elif choice == "2":
            return "full"
        else:
            print("Invalid choice. Please enter 1 or 2.")


def get_auth_choice() -> dict:
    """Get authentication method and credentials from user."""
    print("\n" + "=" * 60)
    print("MOY NALOG API - INTEGRATION TEST")
    print("=" * 60)
    print("\n" + "-" * 40)
    print("Choose authentication method:")
    print("  1. Password (INN + password from nalog.ru)")
    print("  2. SMS (phone number + code)")
    print("-" * 40)

    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice in ("1", "2"):
            break
        print("Invalid choice. Please enter 1 or 2.")

    if choice == "1":
        print("\n" + "-" * 40)
        print("Password Authentication")
        print("-" * 40)
        username = input("Username (INN or phone): ").strip()
        password = getpass.getpass("Password: ")

        if not username or not password:
            print("Error: Username and password are required")
            sys.exit(1)

        return {
            "auth_method": "password",
            "username": username,
            "password": password,
        }
    else:
        print("\n" + "-" * 40)
        print("SMS Authentication")
        print("-" * 40)
        print("Enter phone in format: 79001234567 (11 digits, starting with 7)")
        phone = input("Phone number: ").strip()

        # Clean phone number
        phone = "".join(c for c in phone if c.isdigit())

        if len(phone) != 11 or not phone.startswith("7"):
            print("Error: Phone must be 11 digits starting with 7 (e.g., 79001234567)")
            sys.exit(1)

        return {
            "auth_method": "sms",
            "phone": phone,
        }


def ask_another_test() -> bool:
    """Ask user if they want to run another test."""
    print("\n" + "-" * 40)
    while True:
        choice = input("Run another test? (y/n): ").strip().lower()
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no", ""):
            return False
        else:
            print("Please enter 'y' or 'n'.")


async def run_single_test() -> bool:
    """Run a single test cycle. Returns True if successful."""
    # Get auth method and credentials
    auth_info = get_auth_choice()

    # Get test mode
    test_mode = get_test_mode()
    auth_info["test_mode"] = test_mode

    # Get proxy configuration
    proxy, verify_ssl = get_proxy_choice()
    if proxy:
        auth_info["proxy"] = proxy
    auth_info["verify_ssl"] = verify_ssl

    # Setup output directory
    output_dir = Path("test_output") / datetime.now().strftime("%Y%m%d_%H%M%S")

    # Run tests
    test = IntegrationTest(output_dir)

    try:
        return await test.run(**auth_info)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        test.logger.exception("Unexpected error")
        test.generate_report()
        return False


async def main() -> None:
    """Main entry point."""
    last_success = True

    try:
        while True:
            last_success = await run_single_test()

            if not ask_another_test():
                break

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")

    print("\nGoodbye!")
    sys.exit(0 if last_success else 1)


if __name__ == "__main__":
    asyncio.run(main())

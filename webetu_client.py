"""
WebEtu Meal Reservation Automation Client
Extracted and reverse-engineered from Webetu APK (v2.5.0)

Features:
- WebEtu (PROGRES) authentication (handles raw JWT header)
- Automated DIA, Wilaya, and Residence context resolution
- ONOU SSO authentication (loginpwebetu)
- HMAC-SHA256 request signing per request (anti-replay)
- Listing university restaurants / depots
- Listing and booking meal tickets (Déjeuner, Dîner, Petit-déjeuner)
- Cancellation of reservations
- Graceful duplicate reservation detection
- Optional Telegram notifications
- Built-in daemon mode for automated daily scheduling
"""

import os
import json
import time
import uuid
import hmac
import hashlib
import argparse
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import requests


class WebetuClient:
    HMAC_SECRET = "pUzHUW2WX54uCzhO8JC2eQ6g1Ol21upw"
    DEFAULT_BASE_PROGRES = "https://api-webetu.mesrs.dz"
    DEFAULT_BASE_ONOU = "https://gs-api.onou.dz"

    MEAL_TYPES = {
        "breakfast": 1,
        "lunch": 2,
        "dinner": 3,
        "1": 1,
        "2": 2,
        "3": 3,
    }

    MEAL_NAMES = {
        1: "Petit-déjeuner (Breakfast / فطور)",
        2: "Déjeuner (Lunch / غداء)",
        3: "Dîner (Dinner / عشاء)",
    }

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.username = username
        self.password = password
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "okhttp/4.9.2 Webetu/2.5.0",
            "Accept": "application/json",
        })

        # Base Endpoints
        self.base_progres = self.DEFAULT_BASE_PROGRES
        self.base_onou = self.DEFAULT_BASE_ONOU

        # State
        self.progres_token: Optional[str] = None
        self.student_uuid: Optional[str] = None
        self.annee_academique_id: Optional[int] = None
        self.dia_id: Optional[int] = None
        self.wilaya_id: Optional[int] = None
        self.residence_id: Optional[int] = None
        self.onou_token: Optional[str] = None
        self.student_name: Optional[str] = None

    def _sign_headers(self, data_str: str = "") -> Dict[str, str]:
        """Generates fresh HMAC-SHA256 headers matching the Webetu app."""
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        message = f"{timestamp}|{nonce}|{data_str}".encode("utf-8")
        signature = hmac.new(
            self.HMAC_SECRET.encode("utf-8"),
            message,
            hashlib.sha256
        ).hexdigest()

        return {
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
            "Content-Type": "application/json",
        }

    def send_telegram(self, message: str):
        """Sends an optional Telegram notification if credentials are configured."""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"[!] Warning: Failed to send Telegram notification: {e}", file=sys.stderr)

    def fetch_remote_config(self) -> Dict[str, Any]:
        """Fetches runtime endpoint configuration from the PROGRES API."""
        url = f"{self.base_progres}/api/infos/configuration"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        config = resp.json()
        if "urlApiProgres" in config:
            self.base_progres = config["urlApiProgres"]
        if "urlApiOnou" in config:
            self.base_onou = config["urlApiOnou"]
        return config

    def login_webetu(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Logs into Webetu PROGRES API."""
        user = username or self.username
        pwd = password or self.password
        if not user or not pwd:
            raise ValueError("Username and password are required for login.")

        try:
            self.fetch_remote_config()
        except Exception:
            pass

        url = f"{self.base_progres}/api/authentication/v1/"
        payload = {"username": user, "password": pwd}
        data_str = json.dumps(payload, separators=(",", ":"))

        resp = None
        for attempt in range(1, 4):
            try:
                headers = self._sign_headers(data_str)
                resp = self.session.post(url, data=data_str, headers=headers, timeout=20)
                break
            except Exception as e:
                if attempt == 3:
                    raise
                time.sleep(3 * attempt)

        if resp.status_code != 200:
            raise RuntimeError(f"Webetu login failed ({resp.status_code}): {resp.text}")

        res_data = resp.json()
        self.progres_token = res_data.get("token")
        self.student_uuid = res_data.get("uuid")
        self.username = user

        if not self.progres_token or not self.student_uuid:
            raise RuntimeError(f"Invalid login response: missing token or uuid ({res_data})")

        return True

    def fetch_student_context(self) -> Dict[str, Any]:
        """Fetches academic year, DIA, Wilaya, and Residence info."""
        if not self.progres_token or not self.student_uuid:
            raise RuntimeError("Must be logged into Webetu before fetching student context.")

        # Note: PROGRES API uses raw token in 'authorization' header without 'Bearer ' prefix
        auth_header = {"authorization": self.progres_token}

        # 1. Current Academic Year
        url_year = f"{self.base_progres}/api/infos/AnneeAcademiqueEncours"
        headers = {**auth_header, **self._sign_headers("")}
        resp = self.session.get(url_year, headers=headers, timeout=10)
        resp.raise_for_status()
        year_data = resp.json()
        self.annee_academique_id = year_data.get("id")

        # 2. Student DIA
        url_dia = (
            f"{self.base_progres}/api/infos/bac/{self.student_uuid}/"
            f"anneeAcademique/{self.annee_academique_id}/dia"
        )
        headers = {**auth_header, **self._sign_headers("")}
        resp = self.session.get(url_dia, headers=headers, timeout=10)
        resp.raise_for_status()
        dia_data = resp.json()
        self.dia_id = dia_data.get("id")

        prenom = dia_data.get("individuPrenomLatin", "")
        nom = dia_data.get("individuNomLatin", "")
        self.student_name = f"{prenom} {nom}".strip()

        # Extract residence if housed (check dia then /demandesHebregement)
        hebergements = dia_data.get("hebergement", [])
        for h in hebergements:
            if h.get("idAnneeAcademique") == self.annee_academique_id:
                self.residence_id = h.get("idResidance")
                break

        if not self.residence_id:
            try:
                url_heberg = f"{self.base_progres}/api/infos/bac/{self.student_uuid}/demandesHebregement"
                r_heberg = self.session.get(url_heberg, headers=auth_header, timeout=10)
                if r_heberg.status_code == 200:
                    demandes = r_heberg.json()
                    if isinstance(demandes, list):
                        for d in demandes:
                            if d.get("idAnneeAcademique") == self.annee_academique_id or len(demandes) == 1:
                                self.residence_id = d.get("idResidance")
                                break
            except Exception:
                pass

        # 3. Wilaya Inscription
        url_wilaya = f"{self.base_progres}/api/infos/wilayaInscription/{self.dia_id}"
        headers = {**auth_header, **self._sign_headers("")}
        resp = self.session.get(url_wilaya, headers=headers, timeout=10)
        resp.raise_for_status()
        wilaya_data = resp.json()
        if isinstance(wilaya_data, dict):
            self.wilaya_id = (
                wilaya_data.get("id")
                or (wilaya_data.get("data", {}).get("id") if isinstance(wilaya_data.get("data"), dict) else wilaya_data.get("data"))
            )
        else:
            self.wilaya_id = wilaya_data

        return {
            "uuid": self.student_uuid,
            "student_name": self.student_name,
            "annee_academique_id": self.annee_academique_id,
            "dia_id": self.dia_id,
            "wilaya_id": self.wilaya_id,
            "residence_id": self.residence_id,
        }

    def login_onou(self) -> str:
        """Logs into the ONOU restaurant/services API."""
        if not self.wilaya_id:
            self.fetch_student_context()

        url = f"{self.base_onou}/api/loginpwebetu"
        payload = {
            "uuid": self.student_uuid,
            "wilaya": self.wilaya_id,
            "residence": self.residence_id,
            "token": self.progres_token,
        }
        data_str = json.dumps(payload, separators=(",", ":"))
        headers = self._sign_headers(data_str)

        resp = self.session.post(url, data=data_str, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"ONOU login failed ({resp.status_code}): {resp.text}")

        res_json = resp.json()
        self.onou_token = (
            res_json.get("token")
            or (res_json.get("data", {}).get("token") if isinstance(res_json.get("data"), dict) else None)
        )
        if not self.onou_token:
            raise RuntimeError(f"ONOU response did not contain token: {res_json}")

        return self.onou_token

    def _ensure_onou_session(self):
        if not self.onou_token:
            if not self.progres_token:
                self.login_webetu()
            self.login_onou()

    def get_restaurants(self) -> List[Dict[str, Any]]:
        """Fetches the list of available university restaurants (depots)."""
        self._ensure_onou_session()

        url = f"{self.base_onou}/api/getdepotres"
        params = {
            "uuid": self.student_uuid,
            "wilaya": self.wilaya_id,
            "residence": self.residence_id,
            "token": self.progres_token,
        }
        headers = {
            "authorization": f"Bearer {self.onou_token}",
            **self._sign_headers(""),
        }

        resp = self.session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        depots = []
        if isinstance(data, dict):
            if "depots" in data:
                depots = data["depots"]
            elif isinstance(data.get("data"), dict) and "depots" in data["data"]:
                depots = data["data"]["depots"]
            elif isinstance(data.get("data"), list):
                depots = data["data"]
        return depots

    def get_reservations(self) -> List[Dict[str, Any]]:
        """Fetches currently confirmed meal reservations for the student."""
        self._ensure_onou_session()

        url = f"{self.base_onou}/api/meal-reservations/student"
        params = {
            "uuid": self.student_uuid,
            "wilaya": self.wilaya_id,
            "residence": self.residence_id,
            "token": self.progres_token,
        }
        headers = {
            "authorization": f"Bearer {self.onou_token}",
            **self._sign_headers(""),
        }

        resp = self.session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("data", [])
        return data if isinstance(data, list) else []

    def is_already_reserved(self, date_str: str, meal_type: int) -> bool:
        """Checks if a reservation for the given date and meal type already exists."""
        try:
            reservations = self.get_reservations()
            for r in reservations:
                r_date = str(r.get("date_reserve", ""))
                r_type_fr = str(r.get("mealtype_fr", "")).lower()
                r_type_ar = str(r.get("mealtype_ar", ""))
                # Match by date
                if r_date == str(date_str):
                    if meal_type == 1 and ("petit" in r_type_fr or "فطور" in r_type_ar):
                        return True
                    if meal_type == 2 and ("déjeuner" in r_type_fr or "dejeuner" in r_type_fr or "غداء" in r_type_ar) and "petit" not in r_type_fr:
                        return True
                    if meal_type == 3 and ("dîner" in r_type_fr or "diner" in r_type_fr or "عشاء" in r_type_ar):
                        return True
        except Exception:
            pass
        return False

    def reserve_meals(
        self,
        date_str: str,
        meal_types: List[int],
        depot_id: int
    ) -> Dict[str, Any]:
        """
        Reserves one or more meals for a given date at a specified restaurant/depot.
        Sends individual requests per meal matching the official Webetu mobile client.
        
        :param date_str: Target date in 'YYYY-MM-DD' format (must be 24h ahead).
        :param meal_types: List of meal type IDs (1: Breakfast, 2: Lunch, 3: Dinner).
        :param depot_id: ID of the restaurant / depot.
        """
        self._ensure_onou_session()

        filtered_meals = []
        for m in meal_types:
            if self.is_already_reserved(date_str, m):
                meal_name = self.MEAL_NAMES.get(m, f"Type {m}")
                print(f"[*] Meal '{meal_name}' already reserved for {date_str}. Skipping.")
            else:
                filtered_meals.append(m)

        if not filtered_meals:
            return {"status": "skipped", "message": "All requested meals are already reserved."}

        results = []
        url = f"{self.base_onou}/api/reservemeal"

        for m_type in filtered_meals:
            meal_name = self.MEAL_NAMES.get(m_type, str(m_type))
            details_str = json.dumps({
                "date_reserve": date_str,
                "menu_type": m_type,
                "idDepot": depot_id
            }, separators=(",", ":"))

            payload = {
                "uuid": self.student_uuid,
                "wilaya": self.wilaya_id,
                "residence": self.residence_id,
                "token": self.progres_token,
                "details": [details_str],
            }

            data_str = json.dumps(payload, separators=(",", ":"))
            headers = {
                "authorization": f"Bearer {self.onou_token}",
                **self._sign_headers(data_str),
            }

            try:
                resp = self.session.post(url, data=data_str, headers=headers, timeout=15)
                try:
                    res_json = resp.json()
                except Exception:
                    res_json = {"raw": resp.text}

                err_msg = str(res_json).lower()
                if "duplicate" in err_msg or "déjà une réservation" in err_msg:
                    print(f"[*] Server reported: You already have a reservation for '{meal_name}' on {date_str}.")
                    results.append({"meal": m_type, "status": "already_reserved", "response": res_json})
                    continue

                if resp.status_code not in (200, 201):
                    msg = res_json.get("message") if isinstance(res_json, dict) else str(res_json)
                    print(f"[!] Server rejected '{meal_name}' on {date_str} (HTTP {resp.status_code}): {msg}")
                    results.append({"meal": m_type, "status": "failed", "code": resp.status_code, "response": res_json})
                    continue

                print(f"[+] Confirmed reservation for '{meal_name}' on {date_str} at depot {depot_id}!")
                self.send_telegram(
                    f"✅ *WebEtu Meal Reservation Confirmed!*\n"
                    f"👤 Student: `{self.student_name or self.username}`\n"
                    f"📅 Date: `{date_str}`\n"
                    f"🍽 Meal: {meal_name}\n"
                    f"🏢 Depot ID: `{depot_id}`"
                )
                results.append({"meal": m_type, "status": "success", "response": res_json})

            except Exception as e:
                print(f"[!] Network error reserving '{meal_name}' on {date_str}: {e}")
                results.append({"meal": m_type, "status": "error", "error": str(e)})

        return {"status": "completed", "details": results}

    def cancel_reservation(self, reservation_id: Any) -> Dict[str, Any]:
        """Cancels an existing meal reservation."""
        self._ensure_onou_session()

        url = f"{self.base_onou}/api/reservemeal/{reservation_id}"
        payload = {
            "data": {
                "uuid": self.student_uuid,
                "wilaya": self.wilaya_id,
                "residence": self.residence_id,
                "token": self.progres_token,
            }
        }
        data_str = json.dumps(payload, separators=(",", ":"))
        headers = {
            "authorization": f"Bearer {self.onou_token}",
            **self._sign_headers(data_str),
        }

        resp = self.session.delete(url, data=data_str, headers=headers, timeout=15)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "success", "raw": resp.text}


def run_daemon(client: WebetuClient, target_hour: int, target_minute: int, meals: List[int], depot_id: Optional[int]):
    """Runs a persistent daemon that triggers daily reservations at a specific time."""
    print(f"[*] Starting WebEtu Daemon. Scheduled to run daily at {target_hour:02d}:{target_minute:02d}...")
    while True:
        now = datetime.now()
        target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        print(f"[*] Next auto-reservation scheduled in {wait_seconds / 3600:.1f} hours ({target_time.strftime('%Y-%m-%d %H:%M')}). Waiting...")
        time.sleep(wait_seconds)

        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"[*] [DAEMON TRIGGER] Booking meals for tomorrow: {tomorrow}...")
        try:
            client.login_webetu()
            depot = depot_id
            if not depot:
                depots = client.get_restaurants()
                if depots:
                    depot = depots[0].get("id") or depots[0].get("idDepot")
            if depot:
                res = client.reserve_meals(tomorrow, meals, depot)
                print(f"[+] Reservation result: {res}")
            else:
                print("[!] Error: No depot available.")
        except Exception as e:
            print(f"[!] Daemon reservation error: {e}", file=sys.stderr)
            client.send_telegram(f"❌ *WebEtu Auto-Reservation Error:*\n`{e}`")


def main():
    parser = argparse.ArgumentParser(description="WebEtu Meal Reservation Automation Tool")
    parser.add_argument("-u", "--username", help="Student matricule / username", required=False)
    parser.add_argument("-p", "--password", help="Student password", required=False)
    parser.add_argument("-c", "--config", help="Path to JSON config file with credentials", default="config.json")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: info
    subparsers.add_parser("info", help="Test login and display student profile & dining info")

    # Command: restaurants
    subparsers.add_parser("restaurants", help="List available dining restaurants (depots)")

    # Command: list
    subparsers.add_parser("list", help="List current meal reservations")

    # Command: cancel
    p_cancel = subparsers.add_parser("cancel", help="Cancel a reservation by ID")
    p_cancel.add_argument("id", help="ID of the reservation to cancel")

    # Command: reserve
    p_reserve = subparsers.add_parser("reserve", help="Reserve meals for a date")
    p_reserve.add_argument("--date", help="Date in YYYY-MM-DD format (defaults to tomorrow)", default=None)
    p_reserve.add_argument(
        "--meals",
        nargs="+",
        help="Meal types to book: breakfast, lunch, dinner, all (or 1, 2, 3)",
        default=None
    )
    p_reserve.add_argument("--depot", type=int, help="Restaurant ID (if omitted, uses default from config)", default=None)

    # Command: auto
    p_auto = subparsers.add_parser("auto", help="Automated reservation (e.g. for cron/systemd): books upcoming meals")
    p_auto.add_argument("--days", type=int, help="Specific day offset ahead (e.g. 1 for tomorrow)", default=None)
    p_auto.add_argument("--window", type=int, help="Rolling window of days ahead to scan and reserve (default: 3)", default=3)
    p_auto.add_argument("--depot", type=int, help="Restaurant ID (defaults to config or first available)", default=None)
    p_auto.add_argument(
        "--meals",
        nargs="+",
        help="Meal types to book: breakfast, lunch, dinner, all (defaults to config or all 3)",
        default=None
    )
    p_auto.add_argument("--dinner", action="store_true", help="Include dinner")

    # Command: daemon
    p_daemon = subparsers.add_parser("daemon", help="Run background daemon that reserves daily at a scheduled hour")
    p_daemon.add_argument("--hour", type=int, help="Hour to trigger daily reservation (0-23, default: 20)", default=20)
    p_daemon.add_argument("--minute", type=int, help="Minute to trigger daily reservation (0-59, default: 0)", default=0)
    p_daemon.add_argument("--depot", type=int, help="Restaurant ID (defaults to first)", default=None)
    p_daemon.add_argument(
        "--meals",
        nargs="+",
        help="Meal types to book: breakfast, lunch, dinner, all (defaults to config or all 3)",
        default=None
    )
    p_daemon.add_argument("--dinner", action="store_true", help="Include dinner")

    args = parser.parse_args()

    # Load credentials & settings (CLI args -> Environment Variables -> config.json)
    username = args.username or os.getenv("PROGRES_USERNAME") or os.getenv("WEBETU_USERNAME")
    password = args.password or os.getenv("PROGRES_PASSWORD") or os.getenv("WEBETU_PASSWORD")
    depot_id_default = int(os.getenv("DEFAULT_DEPOT_ID")) if os.getenv("DEFAULT_DEPOT_ID") else None
    default_meals_cfg = [2, 3]  # Default: Lunch (2) and Dinner (3)
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")

    PLACEHOLDERS = {"YOUR_BAC_MATRICULE", "YOUR_PROGRES_PASSWORD", "YOUR_PASSWORD", "YOUR_USERNAME"}

    if not username or not password or username in PLACEHOLDERS:
        username = None if username in PLACEHOLDERS else username
        password = None if password in PLACEHOLDERS else password
        for cfg_path in [args.config, "config.example.json"]:
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    u = cfg.get("username")
                    p = cfg.get("password")
                    if u and u not in PLACEHOLDERS:
                        username = username or u
                    if p and p not in PLACEHOLDERS:
                        password = password or p
                    if "default_depot_id" in cfg and depot_id_default is None:
                        depot_id_default = cfg.get("default_depot_id")
                    if "default_meals" in cfg:
                        default_meals_cfg = cfg.get("default_meals")
                    tg_token = tg_token or cfg.get("telegram_bot_token")
                    tg_chat = tg_chat or cfg.get("telegram_chat_id")
                if username and password:
                    break
            except (FileNotFoundError, json.JSONDecodeError):
                pass

    # Interactive first-time setup if credentials are missing
    if not username or not password:
        if sys.stdin.isatty():
            print("\n" + "=" * 60)
            print("   🎓 WebEtu Meal Reservation - First-Time Setup")
            print("=" * 60)
            print("Please enter your PROGRES / WebEtu credentials.")
            print("(These will be saved securely to 'config.json' on this device)\n")
            try:
                input_user = input("👉 Enter your BAC Matricule / Username (e.g. 2024XXXXXXXX): ").strip()
                input_pass = input("👉 Enter your PROGRES Password: ").strip()
                depot_in = input("👉 Enter Depot ID (press Enter for 312 - Ali Mendjli 04): ").strip()
                depot_val = int(depot_in) if depot_in.isdigit() else (depot_id_default or 312)

                if input_user and input_pass:
                    username = input_user
                    password = input_pass
                    depot_id_default = depot_val
                    new_cfg = {
                        "username": username,
                        "password": password,
                        "default_depot_id": depot_id_default,
                        "default_meals": [2, 3]
                    }
                    with open(args.config, "w", encoding="utf-8") as f:
                        json.dump(new_cfg, f, indent=2)
                    print(f"\n[+] Configuration saved successfully to '{args.config}'!\n")
            except (KeyboardInterrupt, EOFError):
                print("\n[!] Setup cancelled.")
                sys.exit(1)

    if not username or not password:
        print("\n[!] Error: Username and password must be supplied in config.json or via -u/-p")
        print("    Create 'config.json' with your credentials:")
        print('    {\n      "username": "YOUR_MATRICULE",\n      "password": "YOUR_PASSWORD",\n      "default_depot_id": 312\n    }')
        sys.exit(1)

    client = WebetuClient(
        username=username,
        password=password,
        telegram_bot_token=tg_token,
        telegram_chat_id=tg_chat,
    )

    try:
        print(f"[*] Logging in as student {username}...")
        client.login_webetu()
        ctx = client.fetch_student_context()
        print(f"[+] Webetu Authenticated.")
        print(f"    Student: {ctx['student_name'] or 'N/A'}")
        print(f"    UUID:    {ctx['uuid']}")
        print(f"    Wilaya:  {ctx['wilaya_id']}")
        print(f"    Housed:  {'Yes (ID: ' + str(ctx['residence_id']) + ')' if ctx['residence_id'] else 'No (External)'}")

        print("\n[*] Authenticating with ONOU...")
        client.login_onou()
        print("[+] ONOU Authenticated successfully.")

        if args.command == "info" or not args.command:
            depots = client.get_restaurants()
            print(f"\n=== Available Restaurants ({len(depots)}) ===")
            for d in depots:
                d_id = d.get("id") or d.get("idDepot")
                d_name = d.get("nameFR") or d.get("nameAR") or d.get("name")
                meals = []
                if d.get("breakfast"): meals.append("Breakfast")
                if d.get("lunch"): meals.append("Lunch")
                if d.get("dinner"): meals.append("Dinner")
                meals_str = f"[{', '.join(meals)}]" if meals else ""
                print(f"  • ID {d_id:3d}: {d_name} {meals_str}")

            reservations = client.get_reservations()
            print(f"\n=== Current Confirmed Reservations ({len(reservations)}) ===")
            for r in reservations:
                m_label = r.get("mealtype_fr") or r.get("mealtype_ar")
                depot_name = r.get("depot_fr") or r.get("depot_ar")
                can_del = "Yes" if r.get("candelete") else "Locked"
                print(f"  • ID {r.get('id')} | Date: {r.get('date_reserve')} | Meal: {m_label:8s} | Restaurant: {depot_name} | Can Cancel: {can_del}")

        elif args.command == "restaurants":
            depots = client.get_restaurants()
            print(f"\n=== Available Restaurants ({len(depots)}) ===")
            for d in depots:
                d_id = d.get("id") or d.get("idDepot")
                d_name = d.get("nameFR") or d.get("nameAR") or d.get("name")
                print(f"  ID: {d_id:3d} | {d_name}")

        elif args.command == "list":
            reservations = client.get_reservations()
            print(f"\n=== Confirmed Reservations ({len(reservations)}) ===")
            for r in reservations:
                m_label = r.get("mealtype_fr") or r.get("mealtype_ar")
                depot_name = r.get("depot_fr") or r.get("depot_ar")
                can_del = "Yes" if r.get("candelete") else "Locked"
                print(f"  • ID {r.get('id')} | Date: {r.get('date_reserve')} | Meal: {m_label:8s} | Restaurant: {depot_name} | Can Cancel: {can_del}")

        def parse_meals(cli_meals, fallback):
            if cli_meals:
                if "all" in [str(m).lower() for m in cli_meals]:
                    return [1, 2, 3]
                resolved = []
                for m in cli_meals:
                    val = client.MEAL_TYPES.get(str(m).lower())
                    if val and val not in resolved:
                        resolved.append(val)
                return resolved or fallback or [1, 2, 3]
            return fallback or [1, 2, 3]

        if args.command == "cancel":
            print(f"[*] Cancelling reservation {args.id}...")
            res = client.cancel_reservation(args.id)
            print(f"[+] Reservation cancelled. Response: {res}")

        elif args.command == "reserve":
            target_date = args.date
            if not target_date:
                target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            meal_ids = parse_meals(args.meals, default_meals_cfg)

            depot = args.depot or depot_id_default
            if not depot:
                depots = client.get_restaurants()
                if not depots:
                    print("[!] No restaurants found for your account.")
                    sys.exit(1)
                depot = depots[0].get("id") or depots[0].get("idDepot")
                print(f"[*] No depot specified. Using: {depot}")

            print(f"[*] Reserving meals for {target_date} (Meals: {meal_ids}) at depot {depot}...")
            res = client.reserve_meals(target_date, meal_ids, depot)
            print(f"[+] Reservation result: {res}")

        elif args.command == "auto":
            if args.days is not None:
                day_offsets = [args.days]
            else:
                day_offsets = list(range(1, max(1, args.window) + 1))

            meals = parse_meals(args.meals, default_meals_cfg)
            if args.dinner and 3 not in meals:
                meals.append(3)

            depot = args.depot or depot_id_default
            if not depot:
                depots = client.get_restaurants()
                if not depots:
                    print("[!] No restaurants found.")
                    sys.exit(1)
                depot = depots[0].get("id") or depots[0].get("idDepot")

            print(f"[*] Auto-reservation scanning {len(day_offsets)} day(s) ahead (Offsets: {day_offsets})...")
            print(f"    Target Depot: {depot} | Meals: {meals}")

            all_results = {}
            for offset in day_offsets:
                target_date = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
                print(f"\n[*] [Day +{offset}] Processing date {target_date}...")

                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        res = client.reserve_meals(target_date, meals, depot)
                        all_results[target_date] = res
                        break
                    except Exception as ex:
                        print(f"[!] Attempt {attempt}/{max_retries} for {target_date} failed: {ex}")
                        if attempt < max_retries:
                            time.sleep(5)
                        else:
                            all_results[target_date] = {"status": "error", "error": str(ex)}

            print(f"\n[+] Auto-reservation completed for window: {list(all_results.keys())}")

        elif args.command == "daemon":
            meals = parse_meals(args.meals, default_meals_cfg)
            if args.dinner and 3 not in meals:
                meals.append(3)
            depot = args.depot or depot_id_default
            run_daemon(client, args.hour, args.minute, meals, depot)

    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

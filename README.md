# WebEtu Meal Reservation Automation

Reverse-engineered API client and automation script for the Algerian University portal **WebEtu** (PROGRES / MESRS) and **ONOU** Dining Services (Restauration Universitaire).

---

## 🔍 Reverse-Engineering Summary

By analyzing the Hermes bytecode (`assets/index.android.bundle`, bytecode v96) inside `Webetu.apk`, the meal reservation workflow was extracted.

### 1. API Endpoints & Authentication Architecture

| Service | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **PROGRES** | `GET` | `https://api-webetu.mesrs.dz/api/infos/configuration` | Remote configuration & service URLs |
| **PROGRES** | `POST` | `https://api-webetu.mesrs.dz/api/authentication/v1/` | Student login (`username` + `password`), returns `token` & `uuid` |
| **PROGRES** | `GET` | `https://api-webetu.mesrs.dz/api/infos/AnneeAcademiqueEncours` | Current academic year ID |
| **PROGRES** | `GET` | `https://api-webetu.mesrs.dz/api/infos/bac/{uuid}/anneeAcademique/{yearId}/dia` | Student DIA & residence data |
| **PROGRES** | `GET` | `https://api-webetu.mesrs.dz/api/infos/wilayaInscription/{diaId}` | Wilaya ID of registration |
| **ONOU** | `POST` | `https://gs-api.onou.dz/api/loginpwebetu` | ONOU SSO authentication (takes `uuid`, `wilaya`, `residence`, `token`) |
| **ONOU** | `GET` | `https://gs-api.onou.dz/api/getdepotres` | Get list of university restaurants / depots |
| **ONOU** | `GET` | `https://gs-api.onou.dz/api/meal-reservations/student` | List existing meal reservations |
| **ONOU** | `POST` | `https://gs-api.onou.dz/api/reservemeal` | Book / reserve meals |
| **ONOU** | `DELETE` | `https://gs-api.onou.dz/api/reservemeal/{id}` | Cancel a reservation |

---

### 2. Request Signature (`X-Signature`) & Auth Details

- **PROGRES Headers**: `authorization: <token>` (raw JWT without `Bearer ` prefix).
- **ONOU Headers**: `authorization: Bearer <onou_token>`.
- **HMAC-SHA256 Anti-Replay Signature**:
  All requests must include fresh security headers per call:
  - `X-Timestamp`: Current epoch seconds
  - `X-Nonce`: Random UUID v4 string
  - `X-Signature`: Hex digest of `HMAC-SHA256("${timestamp}|${nonce}|${dataStr}", "pUzHUW2WX54uCzhO8JC2eQ6g1Ol21upw")`
  - `Content-Type`: `application/json`

---

### 3. Meal Types & Booking Rules

- **Meal Types**:
  - `1`: Petit-déjeuner (`meal_breakfast`)
  - `2`: Déjeuner (`meal_lunch`)
  - `3`: Dîner (`meal_dinner`)
- **Booking Window**: Reservations must be made **at least 24 hours in advance**.
- **Payload format**:
  ```json
  {
    "uuid": "<student_uuid>",
    "wilaya": "<wilaya_id>",
    "residence": "<residence_id>",
    "token": "<progres_token>",
    "details": [
      "{\"date_reserve\":\"YYYY-MM-DD\",\"menu_type\":2,\"idDepot\":1}"
    ]
  }
  ```
  *(Note: Items in `details` are JSON strings, not raw JSON objects).*

---

## 🚀 Usage

### 1. Configuration (`config.json`)

```json
{
  "username": "YOUR_BAC_MATRICULE",
  "password": "YOUR_PASSWORD",
  "default_depot_id": 312,
  "default_meals": [2, 3]
}
```
*(Tip: Set `"default_depot_id"` to your favorite restaurant ID from the list below so you don't need to pass `--depot` every time).*

---

### 2. CLI Commands

#### View Profile, Available Restaurants & Existing Bookings:
```bash
python3 webetu_client.py info
```

#### List Available Dining Halls (Restaurants):
```bash
python3 webetu_client.py restaurants
```

#### List Existing Reservations:
```bash
python3 webetu_client.py list
```

#### Cancel an existing reservation:
```bash
python3 webetu_client.py cancel <reservation_id>
```

#### Reserve a Meal manually:
```bash
# Reserve tomorrow's lunch at RU ALI MENDJLI 04 (depot ID 312):
python3 webetu_client.py reserve --meals lunch --depot 312

# Reserve lunch and dinner for a specific date:
python3 webetu_client.py reserve --date 2026-11-13 --meals lunch dinner --depot 312
```

#### Automated Mode (Scans 3-day window by default):
```bash
# Automatically checks the upcoming 3-day window, books any unreserved meals,
# and skips already-booked meals:
python3 webetu_client.py auto

# Custom rolling window (e.g. 2 days ahead):
python3 webetu_client.py auto --window 2

# Book specific day ahead only (e.g. tomorrow):
python3 webetu_client.py auto --days 1

# Book specific meals only:
python3 webetu_client.py auto --meals lunch dinner
```

#### Continuous Background Daemon Mode:
```bash
# Runs continuously in background and triggers automatically every day at 20:00:
python3 webetu_client.py daemon --hour 20 --minute 0 --depot 312
```

---

## 🏢 Constantine Depot IDs Reference

| Depot ID | Restaurant / Residence Name | Arabic Name | Meals Supported |
|---|---|---|---|
| **`312`** | **RU ALI MENDJLI 04** | **الإقامة الجامعية علي منجلي 04** | Petit-déjeuner, Déjeuner, Dîner |
| `309` | RU ALI MENDJLI 01 | الإقامة الجامعية علي منجلي 01 | Déjeuner, Dîner |
| `310` | RU ALI MENDJLI 02 | الإقامة الجامعية علي منجلي 02 | Déjeuner, Dîner |
| `311` | RU ALI SAFARI | الإقامة الجامعية علي سفاري | Déjeuner, Dîner |
| `314` | RU ALI MENDJLI 05 (1000 lits) | الإقامة الجامعية 1000 سرير علي منجلي 05 | Petit-déjeuner, Déjeuner, Dîner |
| `308` | RU LALA FATIMA N SOUMER | الإقامة الجامعية لالة فاطمة نسومر | Déjeuner, Dîner |
| `527` | MENTOURI CAMPUS | المجمع الجامعي الإخوة منتوري | Déjeuner |
| `526` | ZARZARA CAMPUS | المجمع الجامعي زرزارة | Déjeuner |

---

## ⏰ Automated Daily Reservation

A **systemd user timer** has been pre-configured and enabled on your machine to automatically run every evening at **20:00**:

```bash
# Check timer status and next scheduled run:
systemctl --user list-timers | grep webetu

# View output / logs:
tail -f reservation.log

# To disable the automation:
systemctl --user disable --now webetu-reserve.timer

# To re-enable it:
systemctl --user enable --now webetu-reserve.timer
```

---

## ☁️ Cloud Automation & MESRS Geo-Restriction Notice

> [!WARNING]
> **MESRS Firewall & Geo-Restriction Notice**:
> The Algerian Ministry server (`api-webetu.mesrs.dz`) blocks or drops connections coming from foreign cloud datacenters (such as Microsoft Azure runners used by standard GitHub Actions, Google Cloud, AWS, etc.). 
> Connecting from outside Algeria or from public cloud runners results in `Connection aborted / Remote end closed connection without response`.
> 
> Therefore, requests **must originate from an Algerian IP address**.

### 3 Recommended Automation Setups:

---

### Option 1: Local Background Service (Active & Configured)
Your PC already has a systemd background timer configured to execute daily at 20:00:
```bash
# Check timer status:
systemctl --user status webetu-reserve.timer

# View reservation logs:
tail -f reservation.log
```

---

### Option 2: Self-Hosted GitHub Runner (Run from GitHub Mobile App)
If you want to trigger reservations from your phone using GitHub Actions, connect your machine as a **Self-Hosted Runner**:
1. On GitHub, go to your repository **Settings** > **Actions** > **Runners** > Click **"New self-hosted runner"**.
2. Choose **Linux** (or Windows) and run the setup commands.
3. Update `.github/workflows/reserve_meals.yml` to use `runs-on: self-hosted`.
4. Now, GitHub Actions runs on your local machine using your domestic Algerian IP!

---

### Option 3: Termux on Android (24/7 Automation on your Phone)
Because your smartphone is always on and connected to Algerian mobile data (Mobilis, Djezzy, Ooredoo) or home Wi-Fi:
1. Install [Termux](https://termux.dev/) from F-Droid.
2. Run:
   ```bash
   pkg update && pkg install git python cronie -y
   git clone https://github.com/fuih/webetu-bot.git
   cd webetu-bot
   bash run.sh
   ```
3. Add a daily cron job:
   ```bash
   crontab -e
   # Add:
   0 20 * * * cd /data/data/com.termux/files/home/webetu-bot && python3 webetu_client.py auto >> reservation.log 2>&1
   ```

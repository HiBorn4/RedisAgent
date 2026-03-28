from loguru import logger
import os
from dotenv import load_dotenv
import json
import redis
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from es_final_flight_payload import es_flight_payload

load_dotenv()

REINR=""

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_TTL = int(os.getenv("REDIS_TTL_SEC", "3600"))  # seconds; default 1 hour

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    # quick connection check (optional)
    redis_client.ping()
    logger.info(f"Connected to Redis at {REDIS_URL}")
except Exception as e:
    redis_client = None
    logger.warning(f"Could not connect to Redis ({REDIS_URL}): {e}. Caching disabled.")

ES_USERNAME = os.getenv("ES_USERNAME", "")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")

EMP_API_KEY = os.getenv("EMP_API_KEY", None)

def check_trip_validity(pernr, dept_date, arr_date, dept_time, arr_time, action="", tripno="0000000000"):
    """
    Calls trip validation endpoint and returns (True, remarks) when trip is valid, else (False, remarks).
    Date inputs expected as 'YYYYMMDD' strings, times as 'HH:MM' or 'HHMM' (we will normalize).
    """
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X"
    }

    # normalize times (remove colon)
    def normalize_time(t):
        if t is None:
            return ""
        t = str(t).strip()
        return t.replace(":", "") if ":" in t else t

    dept_time_norm = normalize_time(dept_time)
    arr_time_norm = normalize_time(arr_time)
    
    base_url = "https://emssq.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV/ES_TRIPVALD"

    url = f"{base_url}(PERNR='{pernr}',DEPT_DATE='{dept_date}',ARR_DATE='{arr_date}',DEPT_TIME='{dept_time_norm}',ARR_TIME='{arr_time_norm}',ACTION='{action}',TRIPNO='{tripno}')?"
    logger.info(f"📡 Calling trip validation: {url}")

    try:
        auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None
        resp = requests.get(url, headers=headers, auth=auth, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error(f"Trip validation request failed: {e}")
        return False, f"Request failed: {e}"

    if resp.status_code == 200:
        try:
            body = resp.json()
        except Exception as e:
            logger.error(f"Trip validation returned non-json: {e}")
            return False, "Invalid response from trip validation service."

        d = body.get("d", body)
        status = d.get("STATUS", "")
        remarks = d.get("REMARKS", "")

        # follow your provided logic:
        if status == "S" and "No trip available for given period" in remarks:
            logger.info(f"Trip validation success: {remarks}")
            return True, remarks
        elif status == "E" and "already exists" in remarks:
            logger.info(f"Trip validation invalid (already exists): {remarks}")
            return False, remarks
        else:
            logger.warning(f"Trip validation unknown status: {status} / {remarks}")
            return False, f"UNKNOWN STATUS: {status}, REMARKS: {remarks}"

    elif resp.status_code == 404:
        logger.info("Trip validation returned 404")
        return False, "Trip validation returned 404 - not found"
    else:
        logger.error(f"Trip validation unexpected status: {resp.status_code}")
        return False, f"Trip validation error: status {resp.status_code}"

def post_es_get(travel: dict):
    """
    Build and POST the ES_GET payload.
    Uses the flight-style payload if travel_mode is 'F' (Flight),
    otherwise uses the normal non-flight payload.
    Absolutely NO fields are removed from either schema.
    """
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Authorization": EMP_API_KEY,
    }
    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    def det_date(val: str) -> str:
        """Format YYYYMMDD -> YYYY-MM-DDT00:00:00."""
        if not val:
            return ""
        v = val
        return f"{v[:4]}-{v[4:6]}-{v[6:]}T00:00:00" if len(v) == 8 and v.isdigit() else v

    is_flight = travel.get("travel_mode", "").upper().startswith("F")
    base_path = Path("es_header.json")
    if not base_path.exists():
        raise FileNotFoundError("es_header.json not found in current directory")
    with base_path.open(encoding="utf-8") as f:
        es_header = json.load(f)

    if is_flight:
        # ---------------- FLIGHT PAYLOAD ----------------
        payload = {
            "FLAG": "",
            "PERNR": es_header["d"]["PERNR"],
            "REINR": es_header["d"]["REINR"],
            "ACTION": "",
            "SEARCHVISIBLE": es_header["d"]["SEARCHVISIBLE"],
            "SEARCHMANDT": es_header["d"]["SEARCHMANDT"],
            "REASON": travel.get("travel_purpose", ""),
            "MOBILE": es_header["d"]["MOBILE"],
            "TRAVADV": es_header["d"]["TRAVADV"],
            "ADDADV": es_header["d"]["ADDADV"],
            "PAYMODE": es_header["d"]["PAYMODE"],
            "LOCSTART": travel.get("origin_city", ""),
            "DATE_BEG": travel.get("start_date", ""),
            "DATE_END": travel.get("end_date", ""),
            "TIME_BEG": travel.get("start_time", ""),
            "TIME_END": travel.get("end_time", ""),
            "LOC_START": travel.get("origin_city", ""),
            "LOCATION_END": travel.get("destination_city", ""),
            "OTHERREASON": "",
            "OLOC_START": "",
            "OLOCATION_END": "",
            "PERSK": es_header["d"]["PERSK"],
            "PERSA": es_header["d"]["PERSA"],
            "NAV_TRAVELDET": [
                {
                    "PERNR": es_header["d"]["PERNR"],
                    "DATE_BEG": det_date(travel.get("start_date", "")),
                    "TIME_BEG": travel.get("start_time", "").replace(":", ""),
                    "DATE_END": det_date(travel.get("end_date", "")),
                    "TIME_END": travel.get("end_time", "").replace(":", ""),
                    "LOCATION_BEG": travel.get("origin_city", ""),
                    "COUNTRY_BEG": travel.get("country_beg", ""),
                    "ORIGIN_CODE": travel.get("origin_code", ""),
                    "LOCATION_END": travel.get("destination_city", ""),
                    "COUNTRY_END": travel.get("country_end", ""),
                    "DEST_CODE": travel.get("destination_code", ""),
                    "TRAVEL_MODE": travel.get("travel_mode", "B"),
                    "TRAVEL_MODE_CODE": travel.get("travel_mode_code", "B"),
                    "TRAVEL_CLASS": travel.get("travel_class", "B"),
                    "TRAVEL_CLASS_TEXT": travel.get("travel_class_text", "AC"),
                    "PREFERRED_FLIGHT": "",
                    "TICKET_METHOD": travel.get("booking_method_code", "1"),
                    "TICK_METH_TXT": travel.get("booking_method", "Self Booked"),
                    "MRC_1_2_WAY_FLAG": "",
                    "ITENARY": "",
                },
                # From Destination to Source
                {
                    "PERNR": es_header["d"]["PERNR"],
                    "DATE_BEG": det_date(travel.get("end_date", "")),
                    "TIME_BEG": travel.get("end_time", "").replace(":", ""),
                    "DATE_END": det_date(travel.get("end_date", "")),
                    "TIME_END": travel.get("end_time", ""),
                    "LOCATION_BEG": travel.get("destination_city", ""),
                    "COUNTRY_BEG": travel.get("country_beg", ""),
                    "ORIGIN_CODE": travel.get("origin_code", ""),
                    "LOCATION_END": travel.get("destination_city", ""),
                    "COUNTRY_END": travel.get("country_end", ""),
                    "DEST_CODE": travel.get("destination_code", ""),
                    "TRAVEL_MODE": travel.get("travel_mode", "B"),
                    "TRAVEL_MODE_CODE": travel.get("travel_mode_code", "B"),
                    "TRAVEL_CLASS": travel.get("travel_class", "B"),
                    "TRAVEL_CLASS_TEXT": travel.get("travel_class_text", "AC"),
                    "PREFERRED_FLIGHT": "",
                    "TICKET_METHOD": travel.get("booking_method_code", "1"),
                    "TICK_METH_TXT": travel.get("booking_method", "Self Booked"),
                    "MRC_1_2_WAY_FLAG": "",
                    "ITENARY": "",
                }
            ],
            "NAV_J12WAY": [],
            "NAV_GETSEARCH": [],
            "NAV_APPROVERS": [],
            "NAV_PREFERRED_FLIGHT": [],
            "NAV_REPRICE": []
        }
    else:
        # ------------- NON-FLIGHT (NORMAL) PAYLOAD -------------
        payload = {
        "ACTION": "",
        "ADDADV": es_header["d"]["ADDADV"],
        "DATE_BEG": travel.get("start_date", ""),
        "DATE_END": travel.get("end_date", ""),
        "FLAG": "",
        "LOC_START": travel.get("origin_city", ""),
        "LOCATION_END": travel.get("destination_city", ""),
        "LOCSTART": travel.get("origin_city", ""),
        "MOBILE": es_header["d"]["MOBILE"],
        "NAV_APPROVERS": [],
        "NAV_GETSEARCH": [],
        "NAV_J12WAY": [],
        "NAV_PREFERRED_FLIGHT": [],
        "NAV_REPRICE": [],
        "NAV_TRAVELDET": [
            {
                "PERNR": es_header["d"]["PERNR"],
                "DATE_BEG": det_date(travel.get("start_date", "")),
                "TIME_BEG": travel.get("start_time", ""),
                "DATE_END": det_date(travel.get("end_date", "")),
                "TIME_END": travel.get("end_time", ""),
                "LOCATION_BEG": travel.get("origin_city", ""),
                "COUNTRY_BEG": travel.get("country_beg", ""),
                "ORIGIN_CODE": travel.get("origin_code", ""),
                "LOCATION_END": travel.get("destination_city", ""),
                "COUNTRY_END": travel.get("country_end", ""),
                "DEST_CODE": travel.get("destination_code", ""),
                "TRAVEL_MODE": travel.get("travel_mode", "B"),
                "TRAVEL_MODE_CODE": travel.get("travel_mode_code", "B"),
                "TRAVEL_CLASS": travel.get("travel_class", "B"),
                "TRAVEL_CLASS_TEXT": travel.get("travel_class_text", "AC"),
                "PREFERRED_FLIGHT": "",
                "MRC_1_2_WAY_FLAG": "",
                "ITENARY": "1",
                "TICKET_METHOD": travel.get("booking_method", "1"),
                "TICK_METH_TXT": travel.get(
                    "booking_method_text", "Self Booked"
                ),
            },
            {
                "PERNR": es_header["d"]["PERNR"],
                "DATE_BEG": det_date(travel.get("end_date", "")),
                "TIME_BEG": travel.get("start_time", ""),
                "DATE_END": det_date(travel.get("end_date", "")),
                "TIME_END": travel.get("end_time", ""),
                "LOCATION_BEG": travel.get("origin_city", ""),
                "COUNTRY_BEG": travel.get("country_beg", ""),
                "ORIGIN_CODE": travel.get("origin_code", ""),
                "LOCATION_END": travel.get("destination_city", ""),
                "COUNTRY_END": travel.get("country_end", ""),
                "DEST_CODE": travel.get("destination_code", ""),
                "TRAVEL_MODE": travel.get("travel_mode", "B"),
                "TRAVEL_MODE_CODE": travel.get("travel_mode_code", "B"),
                "TRAVEL_CLASS": travel.get("travel_class", "B"),
                "TRAVEL_CLASS_TEXT": travel.get("travel_class_text", "AC"),
                "PREFERRED_FLIGHT": "",
                "MRC_1_2_WAY_FLAG": "",
                "ITENARY": "2",
                "TICKET_METHOD": travel.get("booking_method_code", "1"),
                "TICK_METH_TXT": travel.get(
                    "booking_method", "Self Booked"
                ),
            },
        ],
        "OLOC_START": "",
        "OLOCATION_END": "",
        "OTHERREASON": "",
        "PAYMODE": es_header["d"]["PAYMODE"],
        "PERNR": es_header["d"]["PERNR"],
        "PERSA": es_header["d"]["PERSA"],
        "PERSK": es_header["d"]["PERSK"],
        "REASON": travel.get("travel_purpose", ""),
        "REINR": es_header["d"]["REINR"],
        "SEARCHMANDT": es_header["d"]["SEARCHMANDT"],
        "SEARCHVISIBLE": es_header["d"]["SEARCHVISIBLE"],
        "TIME_BEG": travel.get("start_time", ""),
        "TIME_END": travel.get("end_time", ""),
        "TRAVADV": es_header["d"]["TRAVADV"],
    }

    logger.warning(f"ES_GET payload: {payload}")

    # Save for debugging
    try:
        with open("es_get.json", "w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        logger.exception("Failed to write es_get.json (non-fatal)")

    try:
        api_url = "https://emssq.mahindra.com/domestictravel/ES_GET?sap-client=500"
        resp = requests.post(api_url, auth=auth, json=payload, headers=headers, timeout=(500, 1000))

        # ----  PRINT full response  ----
        logger.info("ES_GET raw response (%s): %s", resp.status_code, resp.text)

        # ----  SAVE to disk  ----
        with open("es_get_flight_response.json", "w", encoding="utf-8") as f:
            try:
                json.dump(resp.json(), f, ensure_ascii=False, indent=2)
            except ValueError:
                f.write(resp.text)

        # ✅  NEW: immediately create lean files
        try:
            from pathlib import Path

            RAW_FILE = Path("es_get_flight_response.json")
            OUT_PREF = Path("nav_preferred_lean.json")
            OUT_GETSEARCH = Path("nav_getsearch_lean.json")

            KEYS = ["FLIGHT_NAME", "FLIGHT_NUMBER", "FLIGHT_KEY", "SOURCE_CITY", 
                    "DESTN_CITY", "DURATION", "BAGGAGEREQUEST", "VIA_CITY_NAME", 
                    "VIA_AIRPORT_NAME", "TRAVEL_CLASS", "DEPT_DATE", "DEP_TIME", 
                    "ARR_DATE", "ARR_TIME", "AIR_FARE", "DURATION", "STOPOVERCOUNT",
                    "REFUND_NONREFUND", "TRAVEL_CLASS", "VIA_FLIGHT"
                ]

            def slim(record: dict) -> dict:
                return {k: record.get(k, "") for k in KEYS}

            raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
            pref_full = raw.get("d", {}).get("NAV_PREFERRED_FLIGHT", {}).get("results", [])
            pref_lean = [slim(r) for r in pref_full]
            OUT_PREF.write_text(json.dumps(pref_lean, ensure_ascii=False, indent=2), encoding="utf-8")

            gs_full = raw.get("d", {}).get("NAV_GETSEARCH", {}).get("results", [])
            gs_lean = [slim(r) for r in gs_full]
            OUT_GETSEARCH.write_text(json.dumps(gs_lean, ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info("✅ nav_preferred_lean.json – %d records", len(pref_lean))
            logger.info("✅ nav_getsearch_lean.json  – %d records", len(gs_lean))

        except Exception as e:
            logger.exception("Lean-flight extraction failed (non-fatal): %s", e)

    except requests.exceptions.RequestException as e:
        logger.error(f"ES_GET request failed: {e}")
        return False, f"ES_GET request failed: {e}"

    if resp.status_code == 201:
        logger.info("ES_GET posted successfully (201).")
        return True, None
    else:
        reason = f"ES_GET failed status {resp.status_code}: {resp.text[:400]}"
        logger.error(reason)
        return False, reason
    
    
def post_es_reprice(travel: dict, pernr: str):
    """
    Build full ES_FINAL payload and POST it.
    Uses template defaults and substitutes known travel data.
    """
    
    global REINR

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Authorization": EMP_API_KEY,
    }
    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None
    
    base_path = Path("es_header.json")
    if not base_path.exists():
        raise FileNotFoundError("es_header.json not found in current directory")
    with base_path.open(encoding="utf-8") as f:
        es_header = json.load(f)
    
    base_path = Path("es_get_flight_response.json")
    if not base_path.exists():
        raise FileNotFoundError("es_header.json not found in current directory")
    with base_path.open(encoding="utf-8") as f:
        es_get_flight_response = json.load(f)
    
    es_pref = es_get_flight_response["d"]["NAV_PREFERRED_FLIGHT"]["results"][0]
    es_pref2 = es_get_flight_response["d"]["NAV_PREFERRED_FLIGHT"]["results"][1]

    payload = {
    "PERNR": es_header["d"]["PERNR"],
    "NAV_REP_FLT": [
      {
            "PERNR": es_header["d"]["PERNR"],
            "PRIARITY_FLIGHT": es_pref["PRIARITY_FLIGHT"],
            "FLIGHT_NAME": es_pref["FLIGHT_NAME"],
            "FLIGHT_NUMBER": es_pref["FLIGHT_NUMBER"],
            "SOURCE_CITY": es_pref["SOURCE_CITY"],
            "DESTN_CITY": es_pref["DESTN_CITY"],
            "VIA_FLIGHT": es_pref.get("VIA_FLIGHT", "Direct Flight"),
            "DEPT_DATE": es_pref["DEPT_DATE"],
            "DEP_TIME": es_pref["DEP_TIME"],
            "ARR_DATE": es_pref["ARR_DATE"],
            "ARR_TIME": es_pref["ARR_TIME"],
            "AIR_FARE": es_pref["AIR_FARE"],
            "FLIGHT_KEY": es_pref["FLIGHT_KEY"],
            "ITENARY": es_pref["ITENARY"],
            "ORIGIN_CODE": es_pref["ORIGIN_CODE"],
            "DEST_CODE": es_pref["DEST_CODE"],
            "ONE_WAY_OR_ROUND_TRIP": es_pref.get("ONE_WAY_OR_ROUND_TRIP", "Rou"),
            "FARE_TYPE": es_pref.get("FARE_TYPE", "Check Fare"),
            "FLIGHT_KEY2": es_pref.get("FLIGHT_KEY2", ""),
            "AIR_FARE2": es_pref.get("AIR_FARE2", "0 "),
            "FARETYPE_CHECK": es_pref.get("FARETYPE_CHECK", ""),
            "AIRLINE_LOGO": es_pref.get("AIRLINE_LOGO", "Mltiple.png"),
            "DEPART_HEAD": es_pref.get("DEPART_HEAD", ""),
            "ARRIVAL_HEAD": es_pref.get("ARRIVAL_HEAD", ""),
            "NORMAL_FARE_HEAD": es_pref.get("NORMAL_FARE_HEAD", ""),
            "CORP_FARE_HEAD": es_pref.get("CORP_FARE_HEAD", ""),
            "OPTION_HEAD": es_pref.get("OPTION_HEAD", ""),
            "REFUND_NONREFUND": es_pref.get("REFUND_NONREFUND", "Refundable"),
            "CORP_REFUND_NONREFUND": es_pref.get("CORP_REFUND_NONREFUND", "Corporate"),
            "DURATION": es_pref["DURATION"],
            "DURATION_HEAD": es_pref.get("DURATION_HEAD", ""),
            "FLIGHT_TYPE": es_pref["FLIGHT_TYPE"],
            "FLIGHT_CODE": es_pref["FLIGHT_CODE"],
            "OPTION_ID": es_pref["OPTION_ID"],
            "ISFREEMEAL": es_pref["ISFREEMEAL"],
            "ISSUPPORTFRIQUENTFLIER": es_pref["ISSUPPORTFRIQUENTFLIER"],
            "DEPARTURETERMINAL": es_pref.get("DEPARTURETERMINAL", ""),
            "ARRIVALTERMINAL": es_pref.get("ARRIVALTERMINAL", ""),
            "FAREBASIS": es_pref["FAREBASIS"],
            "BOOKINGCLASS": es_pref["BOOKINGCLASS"],
            "DISPLAYGROUP": es_pref["DISPLAYGROUP"],
            "SEARCHFORMDATA": es_pref["SEARCHFORMDATA"],
            "ISPRIVATEFARE": es_pref["ISPRIVATEFARE"],
            "SEARCHSEGMENTID": es_pref["SEARCHSEGMENTID"],
            "BAGGAGEREQUEST": es_pref.get("BAGGAGEREQUEST", ""),
            "STOPOVERCOUNT": es_pref["STOPOVERCOUNT"],
            "ORIGIN_AIRPORT_NAME": es_pref["ORIGIN_AIRPORT_NAME"],
            "DEST_AIRPORT_NAME": es_pref["DEST_AIRPORT_NAME"],
            "VIA_CITY_NAME": es_pref.get("VIA_CITY_NAME", ""),
            "VIA_CITY_CODE": es_pref.get("VIA_CITY_CODE", ""),
            "VIA_AIRPORT_NAME": es_pref.get("VIA_AIRPORT_NAME", ""),
            "LOWEST_INDICATOR": es_pref.get("LOWEST_INDICATOR", ""),
            "TRAVEL_CLASS": es_pref.get("TRAVEL_CLASS", "")
      },
      {
            "PERNR": es_header["d"]["PERNR"],
            "PRIARITY_FLIGHT": es_pref2["PRIARITY_FLIGHT"],
            "FLIGHT_NAME": es_pref2["FLIGHT_NAME"],
            "FLIGHT_NUMBER": es_pref2["FLIGHT_NUMBER"],
            "SOURCE_CITY": es_pref2["SOURCE_CITY"],
            "DESTN_CITY": es_pref2["DESTN_CITY"],
            "VIA_FLIGHT": es_pref2.get("VIA_FLIGHT", "Direct Flight"),
            "DEPT_DATE": es_pref2["DEPT_DATE"],
            "DEP_TIME": es_pref2["DEP_TIME"],
            "ARR_DATE": es_pref2["ARR_DATE"],
            "ARR_TIME": es_pref2["ARR_TIME"],
            "AIR_FARE": es_pref2["AIR_FARE"],
            "FLIGHT_KEY": es_pref2["FLIGHT_KEY"],
            "ITENARY": es_pref2["ITENARY"],
            "ORIGIN_CODE": es_pref2["ORIGIN_CODE"],
            "DEST_CODE": es_pref2["DEST_CODE"],
            "ONE_WAY_OR_ROUND_TRIP": es_pref2.get("ONE_WAY_OR_ROUND_TRIP", "Rou"),
            "FARE_TYPE": es_pref2.get("FARE_TYPE", "Check Fare"),
            "FLIGHT_KEY2": es_pref2.get("FLIGHT_KEY2", ""),
            "AIR_FARE2": es_pref2.get("AIR_FARE2", "0 "),
            "FARETYPE_CHECK": es_pref2.get("FARETYPE_CHECK", ""),
            "AIRLINE_LOGO": es_pref2.get("AIRLINE_LOGO", "Air-India-Logo.jpg"),
            "DEPART_HEAD": es_pref2.get("DEPART_HEAD", ""),
            "ARRIVAL_HEAD": es_pref2.get("ARRIVAL_HEAD", ""),
            "NORMAL_FARE_HEAD": es_pref2.get("NORMAL_FARE_HEAD", ""),
            "CORP_FARE_HEAD": es_pref2.get("CORP_FARE_HEAD", ""),
            "OPTION_HEAD": es_pref2.get("OPTION_HEAD", ""),
            "REFUND_NONREFUND": es_pref2.get("REFUND_NONREFUND", "Refundable"),
            "CORP_REFUND_NONREFUND": es_pref2.get("CORP_REFUND_NONREFUND", "Corporate"),
            "DURATION": es_pref2["DURATION"],
            "DURATION_HEAD": es_pref2.get("DURATION_HEAD", ""),
            "FLIGHT_TYPE": es_pref2["FLIGHT_TYPE"],
            "FLIGHT_CODE": es_pref2["FLIGHT_CODE"],
            "OPTION_ID": es_pref2["OPTION_ID"],
            "ISFREEMEAL": es_pref2["ISFREEMEAL"],
            "ISSUPPORTFRIQUENTFLIER": es_pref2["ISSUPPORTFRIQUENTFLIER"],
            "DEPARTURETERMINAL": es_pref2.get("DEPARTURETERMINAL", ""),
            "ARRIVALTERMINAL": es_pref2.get("ARRIVALTERMINAL", ""),
            "FAREBASIS": es_pref2["FAREBASIS"],
            "BOOKINGCLASS": es_pref2["BOOKINGCLASS"],
            "DISPLAYGROUP": es_pref2["DISPLAYGROUP"],
            "SEARCHFORMDATA": es_pref2["SEARCHFORMDATA"],
            "ISPRIVATEFARE": es_pref2["ISPRIVATEFARE"],
            "SEARCHSEGMENTID": es_pref2["SEARCHSEGMENTID"],
            "BAGGAGEREQUEST": es_pref2.get("BAGGAGEREQUEST", ""),
            "STOPOVERCOUNT": es_pref2["STOPOVERCOUNT"],
            "ORIGIN_AIRPORT_NAME": es_pref2["ORIGIN_AIRPORT_NAME"],
            "DEST_AIRPORT_NAME": es_pref2["DEST_AIRPORT_NAME"],
            "VIA_CITY_NAME": es_pref2.get("VIA_CITY_NAME", ""),
            "VIA_CITY_CODE": es_pref2.get("VIA_CITY_CODE", ""),
            "VIA_AIRPORT_NAME": es_pref2.get("VIA_AIRPORT_NAME", ""),
            "LOWEST_INDICATOR": es_pref2.get("LOWEST_INDICATOR", ""),
            "TRAVEL_CLASS": es_pref2.get("TRAVEL_CLASS", "")
      }
],
      "NAV_REPRICE": []
}

    logger.warning(f"ES_FINAL payload: {payload}")

    try:
        api_url = "https://emssq.mahindra.com/domestictravel/ES_REPRICE?sap-client=500"
        logger.info(f"Posting to ES_FINAL: {api_url}")
        resp = requests.post(api_url, auth=auth, json=payload, headers=headers, timeout=(250, 300))
    except requests.exceptions.RequestException as e:
        logger.error(f"ES_FINAL request failed: {e}")
        return False, f"ES_FINAL request failed: {e}"



def post_es_final(travel: dict, pernr: str):
    """
    Build full ES_FINAL payload and POST it.
    Uses template defaults and substitutes known travel data.
    """
    
    global REINR

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Authorization": EMP_API_KEY,
    }
    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    def det_date(val):
        # format YYYYMMDD to /Date(ms)/ for NAV_FIN_TO_IT
        if not val:
            return ""
        v = str(val)
        if len(v) == 8 and v.isdigit():
            # convert to epoch ms at midnight
            from datetime import datetime
            dt = datetime.strptime(v, "%Y%m%d")
            return f"/Date({int(dt.timestamp()) * 1000})/"
        return v
    
    base_path = Path("es_header.json")
    if not base_path.exists():
        raise FileNotFoundError("es_header.json not found in current directory")
    with base_path.open(encoding="utf-8") as f:
        es_header = json.load(f)

    base_path = Path("es_get_no_flight.json")
    if not base_path.exists():
        raise FileNotFoundError("es_header.json not found in current directory")
    with base_path.open(encoding="utf-8") as f:
        es_get_no_flight_response = json.load(f)
      
    es_pref = es_get_no_flight_response["d"]["NAV_TRAVELDET"]["results"][0]
    es_pref2 = es_get_no_flight_response["d"]["NAV_TRAVELDET"]["results"][1]

    is_flight = travel.get("travel_mode", "").upper().startswith("F")
    
    if is_flight: 
        payload = es_flight_payload(travel)
    else: 
    
        payload = {
            "ACTION": "",
            "ADDADV": f"{travel.get('additional_advance', 0):.2f}",
            "AGE": es_header["d"]["AGE"],
            "ATTACHMANDT": es_header["d"]["ATTACHMANDT"],
            "ATTACHVISIBLE": es_header["d"]["ATTACHVISIBLE"],
            "COMMENT": "",
            "CREAT_DATE": es_header["d"]["CREAT_DATE"],
            "DATE_BEG": travel.get("start_date", ""),
            "DATE_END": travel.get("end_date", ""),
            "DOB": es_header["d"]["DOB"],
            "EMAIL": travel.get("email", f"{pernr}@MAHINDRA.COM"),
            "FNAME": es_header["d"]["FNAME"],
            "ISSFUSERID": es_header["d"]["ISSFUSERID"],
            "LNAME": es_header["d"]["LNAME"],
            "LOC_START": travel.get("origin_city", ""),
            "LOCATION_END": travel.get("destination_city", ""),
            "MNAME": es_header["d"]["MNAME"],
            "MOBILE": es_header["d"]["MOBILE"],
            "MODE": "",
            "NAV_FIN_BOOK": [],
            "NAV_FIN_COMING": [],
            "NAV_FIN_COST": [
                {
                    "AUFNR": "",
                    "KOSTL": travel.get("cost_center", ""),
                    "PERCENT": "100.00",
                    "POSNR": travel.get("project_wbs", ""),
                    "POSNR2W": "",
                }
            ],
            "NAV_FIN_EMPFLIGHTS": [],
            "NAV_FIN_FILES": [],
            "NAV_FIN_GOING": [],
            "NAV_FIN_J12WAY": [],
            "NAV_FIN_ONEWAY": [],
            "NAV_FIN_REPRICE": [],
            "NAV_FIN_SEGMENT": [],
            "NAV_FIN_TO_IT": [
                [
                {
                "CITY_CLASS": es_pref["CITY_CLASS"],
                "COUNTRY_BEG": es_pref["COUNTRY_BEG"],
                "COUNTRY_END": es_pref["COUNTRY_END"],
                "DATE_BEG": es_pref["DATE_BEG"],
                "DATE_END": es_pref["DATE_END"],
                "DEL_BUTTON_READ_ONLY": es_pref["DEL_BUTTON_READ_ONLY"],
                "DEST_CODE": es_pref["DEST_CODE"],
                "EDIT_BUTTON_READ_ONLY": es_pref["EDIT_BUTTON_READ_ONLY"],
                "ITENARY": es_pref["ITENARY"],
                "LOCATION_BEG": es_pref["LOCATION_BEG"],
                "LOCATION_END": es_pref["LOCATION_END"],
                "MRC_1_2_WAY_FLAG": es_pref["MRC_1_2_WAY_FLAG"],
                "ORIGIN_CODE": es_pref["ORIGIN_CODE"],
                "PERNR": es_pref["PERNR"],
                "PREFERRED_FLIGHT": es_pref["PREFERRED_FLIGHT"],
                "TIME_BEG": es_pref["TIME_BEG"],
                "TIME_END": es_pref["TIME_END"],
                "TRAVEL_CLASS": es_pref["TRAVEL_CLASS"],
                "TRAVEL_CLASS_TEXT": es_pref["TRAVEL_CLASS_TEXT"],
                "TRAVEL_MODE": es_pref["TRAVEL_MODE"],
                "TRAVEL_MODE_CODE": es_pref["TRAVEL_MODE_CODE"],
                "TICK_METH_TXT": es_pref["TICK_METH_TXT"],
                "TICKET_METHOD": es_pref["TICKET_METHOD"]
                },
                {
                "CITY_CLASS": es_pref2["CITY_CLASS"],
                "COUNTRY_BEG": es_pref2["COUNTRY_BEG"],
                "COUNTRY_END": es_pref2["COUNTRY_END"],
                "DATE_BEG": es_pref2["DATE_BEG"],
                "DATE_END": es_pref2["DATE_END"],
                "DEL_BUTTON_READ_ONLY": es_pref2["DEL_BUTTON_READ_ONLY"],
                "DEST_CODE": es_pref2["DEST_CODE"],
                "EDIT_BUTTON_READ_ONLY": es_pref2["EDIT_BUTTON_READ_ONLY"],
                "ITENARY": es_pref2["ITENARY"],
                "LOCATION_BEG": es_pref2["LOCATION_BEG"],
                "LOCATION_END": es_pref2["LOCATION_END"],
                "MRC_1_2_WAY_FLAG": es_pref2["MRC_1_2_WAY_FLAG"],
                "ORIGIN_CODE": es_pref2["ORIGIN_CODE"],
                "PERNR": es_pref2["PERNR"],
                "PREFERRED_FLIGHT": es_pref2["PREFERRED_FLIGHT"],
                "TIME_BEG": es_pref2["TIME_BEG"],
                "TIME_END": es_pref2["TIME_END"],
                "TRAVEL_CLASS": es_pref2["TRAVEL_CLASS"],
                "TRAVEL_CLASS_TEXT": es_pref2["TRAVEL_CLASS_TEXT"],
                "TRAVEL_MODE": es_pref2["TRAVEL_MODE"],
                "TRAVEL_MODE_CODE": es_pref2["TRAVEL_MODE_CODE"],
                "TICK_METH_TXT": es_pref2["TICK_METH_TXT"],
                "TICKET_METHOD": es_pref2["TICKET_METHOD"]
                }
                ]
            ],
            "NO_VALIDATIONS": "X",
            "OLOC_START": es_get_no_flight_response["d"]["OLOC_START"],
            "OLOCATION_END": es_get_no_flight_response["d"]["OLOCATION_END"],
            "OTHERREASON": es_get_no_flight_response["d"]["OTHERREASON"],
            "PAYMODE": es_get_no_flight_response["d"]["PAYMODE"],
            "PERNR": es_get_no_flight_response["d"]["PERNR"],
            "PERSA": es_get_no_flight_response["d"]["PERSA"],
            "PERSK": es_get_no_flight_response["d"]["PERSK"],
            "REASON": travel.get("travel_purpose", ""),
            "REINR": es_get_no_flight_response["d"]["REINR"],
            "SEARCHMANDT": es_get_no_flight_response["d"]["SEARCHMANDT"],
            "SEARCHMODE": es_header["d"]["SEARCHMODE"],
            "SEARCHVISIBLE": es_get_no_flight_response["d"]["SEARCHVISIBLE"],
            "SEX": es_header["d"]["SEX"],
            "TIME_BEG": travel.get("start_time", ""),
            "TIME_END": travel.get("end_time", ""),
            "TITLE": es_header["d"]["TITLE"],
            "TRAVADV": f"{travel.get('travel_advance', 0):.2f}",
            "TRIPDEL": es_header["d"]["TRIPDEL"],
            "TRIPEDIT": es_header["d"]["TRIPEDIT"],
            "WAERS": es_header["d"]["WAERS"],
            "WBSMAND": es_header["d"]["WBSMAND"],
        }

    logger.warning(f"ES_FINAL payload: {payload}")

    try:
        api_url = "https://emssq.mahindra.com/domestictravel/ES_FINAL"
        logger.info(f"Posting to ES_FINAL: {api_url}")
        resp = requests.post(api_url, auth=auth, json=payload, headers=headers, timeout=(250, 300))
    except requests.exceptions.RequestException as e:
        logger.error(f"ES_FINAL request failed: {e}")
        return False, f"ES_FINAL request failed: {e}"

    # ---- NEW: extract REINR from SAP response ----
    if resp.status_code in {200, 201}:
        try:
            sap_answer = resp.json()          # OData JSON
            reinr = sap_answer["d"]["REINR"]  # Trip number SAP just created
            REINR = reinr     # keep it for later use
            logger.info(f"SAP trip created successfully – REINR: {reinr}")
            return True, None
        except (KeyError, ValueError) as e:
            logger.warning(f"Could not extract REINR from SAP reply: {e}")
            return True, None                 # still success, just no number
    else:
        reason = f"ES_FINAL failed status {resp.status_code}: {resp.text[:400]}"
        logger.error(reason)
        return False, reason

# def cancel_trip(trip_json: dict):
#     """
#     Calls ES_TRIP_CANCEL endpoint to cancel a trip.
#     Expects trip_json with:
#         {
#             "employee_id": "<8-digit ID>",
#             "trip_num": "<Trip number>"
#         }
#     Returns (True, dict) on success else (False, reason)
#     """
#     pernr = trip_json.get("employee_id", "")
#     tripno = trip_json.get("trip_num", "")
#     comments = "Trip cancellation requested by user"

#     base_url = "https://emssq.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV"
#     endpoint = f"/ES_TRIP_CANCEL(PERNR='{pernr}',TRIPNO='{tripno}',COMMENTS='{comments}')?"
#     url = base_url + endpoint

#     headers = {
#         "Accept": "application/json",
#         "X-Requested-With": "X"
#     }

#     try:
#         auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None
#         resp = requests.get(url, headers=headers, auth=auth, timeout=10)
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Trip cancel request failed: {e}")
#         return False, f"Request failed: {e}"

#     if resp.status_code == 200:
#         try:
#             data = resp.json().get("d", {})
#             result = {
#                 "MESSAGE_TYPE": data.get("MESSAGE_TYPE", ""),
#                 "MESSAGE": data.get("MESSAGE", "")
#             }
#             logger.info(f"Trip cancel success: {result}")
#             return True, result
#         except Exception as e:
#             return False, f"Invalid JSON response: {e}"
#     else:
#         reason = f"Request failed with status code {resp.status_code}"
#         logger.error(reason)
#         return False, reason
#supabase_utils.py
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone
import bcrypt
from uuid import uuid4
from typing import Optional
from dateutil.parser import parse as parse_date
import contextvars
from fastapi import Request, HTTPException, status
import jwt
import json
import re
from zoneinfo import ZoneInfo
from dateutil import parser
from dotenv import load_dotenv
load_dotenv()

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# JWT Authentication
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")



def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def register_doctor_user(req):
    data = {
        "fname": req.fname,
        "lname": req.lname,
        "emailid": req.emailid,
        "password": hash_password(req.password),
        "mobilenumber": req.mobilenumber,
        "location1": req.location1,
        "city": req.city,
        "province": req.province,
        "country": req.country,
        "medical_license_number": req.medical_license_number,
        "specialization": req.specialization,
        "uuid": str(uuid4()),
        "mname": "",
        "dlnumber": "",
        "verification": 0,
        "availability": 1
    }
    return supabase.table("doctors_registration").insert(data).execute()


def register_patient_user(req):
    data = {
        "fname": req.fname,
        "lname": req.lname,
        "emailid": req.emailid,
        "password": hash_password(req.password),
        "mobilenumber": req.mobilenumber,
        "city": req.city,
        "province": req.province,
        "address": req.address,
        "uuid": str(uuid4()),
        "mname": "",
        "bloodgroup": "",
        "gender": "",
        "height": "",
        "weight": "",
        "race": "",
        "hcardnumber": "",
        "passportnumber": "",
        "prnumber": "",
        "dlnumber": "",
        "verification": 0
    }
    return supabase.table("patients_registration").insert(data).execute()

################[Both] User identification related functions################

# Define a contextvar to store the current user UUID in the request context
_current_user_uuid: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_uuid")


def set_current_user_uuid(uuid: str) -> None:
    _current_user_uuid.set(uuid)


def current_user_uuid() -> str:
    try:
        return _current_user_uuid.get()
    except LookupError:
        raise RuntimeError(
            "current_user_uuid is not set! Please call set_current_user_uuid() after authentication is complete."
        )


def get_user_by_uuid_and_role(uuid: str, role: str):
    table = "doctors_registration" if role == "doctor" else "patients_registration"
    res = supabase.table(table).select("id, uuid, fname, lname, emailid").eq("uuid", uuid).maybe_single().execute()
    return res.data if res and res.data else None


def login_user(emailid: str, password: str):

    user = None
    role = None

    doc_res = supabase.table("doctors_registration") \
        .select("id, uuid, password, emailid, fname, lname") \
        .eq("emailid", emailid) \
        .maybe_single().execute()
    if doc_res and doc_res.data:
        user = doc_res.data
        role = "doctor"
    else:
        pat_res = supabase.table("patients_registration") \
            .select("id, uuid, password, emailid, fname, lname") \
            .eq("emailid", emailid) \
            .maybe_single().execute()
        if pat_res and pat_res.data:
            user = pat_res.data
            role = "patient"

    if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return None, "Invalid credentials"

    payload = {
        "sub": user["uuid"],
        "role": role,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp()) # valid for 8 hours
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "access_token": token,
        "user": {
            "id": user["id"],
            "emailid": user["emailid"],
            "role": role,
            "fname": user.get("fname", ""),   
            "lname": user.get("lname", ""),
        }
    }, None


def auth_dependency(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth header")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    set_current_user_uuid(payload["sub"])
    return {"uuid": payload["sub"], "role": payload["role"]}


def get_user_info_by_email(emailid: str, role: str):
    table = "doctors_registration" if role == "doctor" else "patients_registration"
    key = "emailid"
    res = supabase.table(table).select("emailid, fname, lname").eq(key, emailid).single().execute()
    if res.data:
        return {
        "emailid": res.data["emailid"],
        "fname": res.data["fname"],
        "lname": res.data.get("lname", ""),
        "role": role
        }
    return None


################[Patients] booking related functions################
##Idempotence, concurrency, slot state atomicity##
def book_slot(patient_id: int, time_segment_id: int, description: str = None):
    """
    Atomically schedules a slot. After a successful appointment, write doctor_appointment.
    """
    segment = supabase.table("doctor_available_time_segments") \
        .select("doctor_id") \
        .eq("id", time_segment_id) \
        .maybe_single().execute()

    if not segment or not segment.data:
        raise ValueError("Segment not found")

    #doctor_id = segment.data["doctor_id"]

    resp = supabase.rpc("book_appointment_atomic", {
        "p_segment_id": time_segment_id,
        "p_patient_id": patient_id
    }).execute()

    if not resp.data or len(resp.data) == 0:
        raise RuntimeError("No data returned from booking RPC")

    appt = resp.data[0]
    print(f"[BOOKED] Appointment booked: segment_id={time_segment_id}, patient_id={patient_id}, appointment_id={appt.get('appointment_id')}")

    return appt



##Idempotence, concurrency, slot state atomicity##
def cancel_appointment(appointment_id: int, by_doctor: bool = False):
    """
    Call the PG transaction function to atomically cancel the reservation and roll back the segment status.
    Returns: (True, None) if success; (None, error_code) if failed.
    """
    try:
        resp = supabase.rpc("cancel_appointment_atomic", {
            "appt_id": appointment_id,
            "by_doctor": by_doctor
        }).execute()

        if resp.data and (resp.data == "OK" or (isinstance(resp.data, list) and "OK" in resp.data)):
            return True, None
        return None, "UNKNOWN_CANCEL_ERROR"
    except Exception as e:
        msg = str(e)
        if "No such appointment" in msg:
            return None, "CANCEL_APPOINTMENT_NOT_FOUND"
        return None, "INTERNAL_CANCEL_ERROR"


##Idempotence, concurrency, slot state atomicity##
def reactivate_time_segment(time_segment_id: int):
    """
    Restore a time segment from blocked (-1) to available (0).
    Raises ValueError on any failure.
    """
    try:
        resp = supabase.rpc("reactivate_time_segment_atomic", {
            "segment_id": time_segment_id
        }).execute()
    except Exception as e:
        raise ValueError(str(e))

    result = resp.data
    if result != "OK" and (not isinstance(result, list) or result[0] != "OK"):
        if "can only be reactivated" in str(result):
            raise ValueError("TIME_SEGMENT_STATUS_INVALID_FOR_REACTIVATE")
        raise ValueError("UNKNOWN_TIME_SEGMENT_REACTIVATE_ERROR")


def get_patient_appointments(patient_id: int):
    return supabase.table("doctor_appointment") \
        .select("*, doctors_registration(fname, lname)") \
        .eq("patient_id", patient_id) \
        .execute()


################[Doctors] Event realted functions################
##Idempotence, concurrency, slot state atomicity##
def create_doctor_event(time_segment_id: int, doctor_id: int, description: str):
    """
    Doctors create self-use events (blocks), based on the create_appointment_request_atomic RPC.
    """
    try:
        resp = supabase.rpc("create_appointment_request_atomic", {
            "p_segment_id": time_segment_id,
            "p_doctor_id": doctor_id,
            "p_request_description": description
        }).execute()
        if isinstance(resp.data, dict) and "time_segment_id" in resp.data:
            return resp.data, None
        else:
            return None, "UNKNOWN_EVENT_CREATE_ERROR"
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e).lower()
        if "requests can only be created for available time segments" in msg:
            return None, "EVENT_SEGMENT_NOT_AVAILABLE"
        return None, msg


def get_doctor_schedule(doctor_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict]:
    """
    Returns doctor's schedule segments enriched with appointment or event information.
    """

    from_date = parse_date(start_date).date() if start_date else None
    to_date = parse_date(end_date).date() if end_date else None

    try:
        res = (
            supabase.table("doctor_available_time_segments")
            .select("id, start_time, end_time, status")
            .eq("doctor_id", doctor_id)
            .order("start_time", desc=False)
            .execute()
        )
        segments = res.data or []

        def in_range(s):
            dt = parse_date(s["start_time"]).date()
            return (not from_date or dt >= from_date) and (not to_date or dt <= to_date)
        segments = [s for s in segments if in_range(s)]

        enriched = []
        for seg in segments:
            item = {
                "segment_id": seg["id"],
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "status": seg["status"],
                "label": {
                    -1: "Blocked",
                    0: "Available",
                    1: "Booked"
                }.get(seg["status"], "Unknown"),
                "patient": None,
                "event_description": None
            }

            if seg["status"] == 1:
                appt_res = (
                    supabase.table("doctor_appointment")
                    .select("patient_id")
                    .eq("time_segment_id", seg["id"])
                    .eq("status", 1)
                    .limit(1)
                    .execute()
                )
                appt = appt_res.data[0] if appt_res.data else None
                if appt:
                    patient_res = (
                        supabase.table("patients_registration")
                        .select("fname, fname")
                        .eq("id", appt["patient_id"])
                        .limit(1)
                        .execute()
                    )
                    patient = patient_res.data[0] if patient_res.data else {}
                    item["patient"] = f"{patient.get('fname', '')} {patient.get('lname', '')}".strip()

            elif seg["status"] == -1:
                event_res = (
                    supabase.table("doctor_appointment_requests")
                    .select("description")
                    .eq("time_segment_id", seg["id"])
                    .eq("status", 0)
                    .limit(1)
                    .execute()
                )
                if event_res.data:
                    item["event_description"] = event_res.data[0].get("description")

            enriched.append(item)

        return enriched

    except Exception as e:
        print(f"[get_doctor_schedule] Failed to fetch schedule: {e}")
        return []


def get_doctor_appointments(doctor_id: int):
    return supabase.table("doctor_appointment") \
        .select("*, patients_registration(fname, lname)") \
        .eq("doctor_id", doctor_id) \
        .execute()


def get_family_doctor_id(patient_id: int) -> int:

    response = supabase.table("patient_doctor") \
        .select("doctor_id") \
        .eq("patient_id", patient_id) \
        .eq("relationship_status", "active") \
        .limit(1) \
        .execute()

    data = response.data
    if not data or not data[0].get("doctor_id"):
        raise ValueError(f"No active family doctor found for patient_id={patient_id}")

    return data[0]["doctor_id"]


def get_family_doctor(patient_id: int) -> dict:
    """
    Get the complete information of the family doctor bound to the patient (requires relationship_status='active')

    Returns:
        {
            "id": 5,
            "fname": "Ali",
            "lname": "Reza",
            "emailid": "...",
            ...
        }
    """
    response = (
        supabase.table("patient_doctor")
        .select("doctor_id, doctors_registration(*)")
        .eq("patient_id", patient_id)
        .eq("relationship_status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )

    data = response.data
    if not data or not data.get("doctors_registration"):
        raise ValueError(f"No active family doctor found for patient_id={patient_id}")

    return data["doctors_registration"]


def cancel_event(segment_id: int, doctor_id: int) -> tuple[str | None, str | None]:
    """
    Cancel a doctor_appointment_request for a segment_id
    """

    try:
        seg_res = supabase.table("doctor_available_time_segments") \
            .select("start_time") \
            .eq("id", segment_id) \
            .maybe_single().execute()
        segment_time = seg_res.data.get("start_time") if seg_res.data else None

        req_res = supabase.table("doctor_appointment_requests") \
            .select("id") \
            .eq("time_segment_id", segment_id) \
            .eq("doctor_id", doctor_id) \
            .eq("status", 1) \
            .maybe_single().execute()

        request_id = req_res.data.get("id") if req_res.data else None
        if not request_id:
            return None, "REQUEST_NOT_FOUND"

        resp = supabase.rpc("cancel_appointment_request_atomic", {
            "doctorid": doctor_id,
            "segmentid": segment_id
        }).execute()
        print(f"[DEBUG] cancel_appointment_request_atomic RPC response: {resp.data}")
        result = resp.data
        print(f"[DEBUG] cancel_appointment_request_atomic RPC response: {result}")

        if result != "OK" and (not isinstance(result, list) or result[0] != "OK"):
            print(f"[ERROR] Unknown cancel error, response={result}")
            return None, "UNKNOWN_EVENT_CANCEL_ERROR"

        print(f"[DEBUG] Successfully cancelled request {request_id}")
        return segment_time, None

    except Exception as e:
        msg = str(e)
        print(f"[EXCEPTION] Cancel event failed: {msg}")
        return None, msg
    

################[Both] Get/View/List slots ################

def parse_timezone(tz_str: str):
    """Parse various time zone formats and return time zone objects"""
    try:
        # Handles UTC offset formats (e.g. "+08:00", "-05:00")
        if re.match(r"^[+-]\d{2}:\d{2}$", tz_str):
            sign = -1 if tz_str.startswith("-") else 1
            hours, minutes = map(int, tz_str[1:].split(":"))
            return timezone(timedelta(hours=sign*hours, minutes=sign*minutes))
        
        # Handling IANA time zone names (such as "Asia/Shanghai")
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("UTC") 


def slot_matches_time_with_tz(dt: datetime, time_pref: str, user_tz: str) -> bool:
    try:
        time_pref = time_pref.strip().lower()
        user_zone = parse_timezone(user_tz)  
        local_dt = dt.astimezone(user_zone)
        
        if time_pref == "morning":
            return local_dt.hour < 12
        elif time_pref == "afternoon":
            return 12 <= local_dt.hour < 17
        elif time_pref == "evening":
            return 17 <= local_dt.hour < 21
        return True
    except Exception as e:
        print(f"[ERROR] Time processing failed: {e}")
        return True  


def get_next_available_slots(
    doctor_id: int,
    days_ahead: int = 7,
    time_pref: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    user_tz: Optional[str] = "+00:00",
):

    if start_iso and end_iso:
        window_start = parse_date(start_iso).astimezone(timezone.utc)
        window_end   = parse_date(end_iso).astimezone(timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        window_start = now
        window_end   = now + timedelta(days=days_ahead)

  
    resp = supabase.table("doctor_available_time_segments")\
        .select("id, doctor_id, start_time, end_time")\
        .eq("doctor_id", doctor_id)\
        .eq("status", 0)\
        .gte("start_time", window_start.isoformat())\
        .lte("start_time", window_end.isoformat())\
        .execute()

    results = []
    for segment in resp.data:
        try:
            segment_start = parse_date(segment["start_time"]).astimezone(timezone.utc)
        except Exception as e:
            print(f"Skipping invalid segment {segment.get('id')}: {e}")
            continue


        if slot_matches_time_with_tz(segment_start, time_pref, user_tz):
            results.append(segment)

    print(f"Found {len(results)} segments for doctor {doctor_id}, time_pref={time_pref or 'anytime'}")
    return results


def get_slot_mapping(session_id: str) -> dict[int, int]:
    """
    Extract the mapping from slot_index to segment_id from the most recent record in the conversations table containing available_slots.
    Supports {index, segment_id} or {index, id} in slot.
    """
    try:
        response = supabase.table("conversations") \
            .select("meta") \
            .eq("session_id", session_id) \
            .order("created_at", desc=True) \
            .limit(5) \
            .execute()

        for row in response.data or []:
            meta_raw = row.get("meta")

            if isinstance(meta_raw, str):
                try:
                    meta = json.loads(meta_raw)
                except json.JSONDecodeError:
                    print("[SLOT MAP ERROR] meta JSON decode failed")
                    continue
            elif isinstance(meta_raw, dict):
                meta = meta_raw
            else:
                print("[SLOT MAP ERROR] meta is not dict or JSON string")
                continue

            available_slots = meta.get("available_slots")
            if not available_slots:
                continue

            mapping = {}
            for slot in available_slots:
                try:
                    index = int(slot["index"])
                    segment_id = int(slot.get("segment_id") or slot.get("id"))
                    mapping[index] = segment_id
                except Exception as e:
                    print(f"[SLOT MAP ERROR] Invalid slot format: {e}, raw slot: {slot}")
                    continue

            if mapping:
                return mapping

    except Exception as e:
        print(f"[SLOT MAP ERROR] Supabase query failed: {e}")

    print(f"[SLOT MAP] No valid available_slots mapping found for session {session_id}")
    return {}


def get_available_segments(preferred_date=None, preferred_time=None, topn=5, user=None, days_ahead=0):

    if not user or "id" not in user or user.get("role") != "patient":
        raise ValueError("Only patients can fetch available segments")

    patient_id = user["id"]
    doctor_id = get_family_doctor_id(patient_id)
    user_tz = user.get("timezone", "+00:00")

    all_segments = []

    slots = []

    # Step 1: Prioritize the specified date (and range if days_ahead is provided)
    if preferred_date:
        if days_ahead:
            # Range mode: preferred_date + range
            start_date = parser.parse(preferred_date)
            end_date = start_date + timedelta(days_ahead)

            slots = get_next_available_slots(
                doctor_id=doctor_id,
                start_iso=start_date.isoformat(),
                end_iso=end_date.isoformat(),
                time_pref=preferred_time,
                user_tz=user_tz
            )
            print(f"[DEBUG] Found {len(slots)} slots from {preferred_date} for {days_ahead} days")
        else:
            # Single-day mode
            slots = get_next_available_slots(
                doctor_id=doctor_id,
                start_iso=preferred_date + "T00:00:00Z",
                end_iso=preferred_date + "T23:59:59Z",
                time_pref=preferred_time,
                user_tz=user_tz
            )
            print(f"[DEBUG] Found {len(slots)} slots on preferred_date {preferred_date}")

    # Step 2: If no slot is found, fallback to checking in the next few days from today
    if not slots:
        slots = get_next_available_slots(
            doctor_id=doctor_id,
            days_ahead=days_ahead,
            time_pref=preferred_time,
            user_tz=user_tz
        )
        print(f"[DEBUG] Fallback: found {len(slots)} slots in next {days_ahead} days")

    # Step 3: Filter available slots with status = 0
    for s in slots:
        if s.get("status", 0) == 0:
            s = s.copy()
            s["doctor_name"] = "Your Family Doctor"
            all_segments.append(s)

    all_segments = sorted(all_segments, key=lambda s: s["start_time"])
    return all_segments[:topn]



def find_matching_appointments(user_id: int, role: str, target: str, target_date: str | None = None):
    """
    Returns a list of matching appointment dicts.

    Each dict contains: appointment_id, appointment_time, status
    """
    now = datetime.now(timezone.utc)
    column = "patient_id" if role == "patient" else "doctor_id"

    try:
        res = (
            supabase.table("doctor_appointment")
            .select("appointment_id, appointment_time, status")
            .eq(column, user_id)
            .execute()
        )
    except Exception as e:
        print(f"[ERROR] Failed to fetch appointments: {e}")
        return []

    matches = []
    for appt in res.data:
        try:
            dt = parse_date(appt["appointment_time"]).astimezone(timezone.utc)
            if appt.get("status") != 1:
                continue  

            if target == "next" and dt >= now:
                matches.append(appt)
            elif target == "date" and target_date and dt.strftime("%Y-%m-%d") == target_date:
                matches.append(appt)
        except Exception as e:
            print(f"[WARN] Skipping invalid appt: {e}")
            continue

    return matches


def is_exact_time_string(time_str: str) -> bool:
    """
    Determines whether the string is in the "HH:MM" exact time format.
    """
    if not isinstance(time_str, str):
        return False
    return re.fullmatch(r"\d{1,2}:\d{2}", time_str.strip()) is not None


def find_matching_events(doctor_id: int, preferred_date: str, preferred_time: str, user_tz, debug: bool = True) -> list[dict]:
 
    if debug:
        print(f"[DEBUG] Looking for doctor {doctor_id}'s events on {preferred_date} with time_pref={preferred_time}, tz={user_tz}")

    schedule = get_doctor_schedule(doctor_id, start_date=preferred_date, end_date=preferred_date)
    if debug:
        print(f"[DEBUG] Retrieved {len(schedule)} segments for date {preferred_date}")

    matches = []
    for s in schedule:
        if s.get("status") != -1:  
            continue

        try:
            dt = parse_date(s["start_time"]).astimezone(user_tz)

            if is_exact_time_string(preferred_time):
                if dt.strftime("%H:%M") == preferred_time:
                    matches.append({"segment_id": s["segment_id"], "start_time": s["start_time"]})
            else:
                if slot_matches_time_with_tz(dt, preferred_time, user_tz):
                    matches.append({"segment_id": s["segment_id"], "start_time": s["start_time"]})
        except Exception as e:
            print(f"[WARN] Skipping invalid segment: {e}")
            continue

    print(f"[DEBUG] find_matching_events → {len(matches)} matching events")
    return matches


################ Others ################

def log_conversation(
    session_id: str,
    patient_id: int | None,
    doctor_id: int | None,
    role: str,
    input: str,
    response: str,
    input_mode: str = "text",
    meta: dict = None
):
    payload = {
        "session_id": session_id,
        "role": role,
        "input": input,
        "response": response,
        "input_mode": input_mode,
    }

    if patient_id is not None:
        payload["patient_id"] = patient_id
    if doctor_id is not None:
        payload["doctor_id"] = doctor_id
    if meta:
        payload["meta"] = meta

    try:
        supabase.table("conversations").insert(payload).execute()
    except Exception as e:
        print(f"[LOG ERROR] Failed to log conversation: {e}")
        print("[PAYLOAD]", json.dumps(payload, indent=2))


def delete_conversations(session_id: str):
    supabase.table("conversations").delete().eq("session_id", session_id).execute()


def get_memory_history(session_id: str, limit: int = 6) -> list[dict]:
    response = supabase.table("conversations") \
        .select("role,input,response") \
        .eq("session_id", session_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .execute()

    data = response.data or []
    if not data:
        print(f"[MEMORY] No history found for session {session_id}")

    history = []
    for row in data:
        role = row["role"]
        if role not in ("user", "assistant", "system", "tool"):
            role = "user"

        history.append({"role": role, "content": row["input"]})
        if row.get("response"):
            history.append({"role": "assistant", "content": row["response"]})
    return history


def save_slot_mapping(
    session_id: str,
    mapping: dict[int, int],
    patient_id: int,
    doctor_id: int,
    role: str = "assistant",
    input_mode: str = "system"
):
    """
    Write the mapping of slot_index → segment_id to the conversations.meta field (as latest memory)
    """
    payload = {
        "session_id": session_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "role": role,
        "input": "[slot_mapping]",
        "response": "[slot_mapping]",
        "input_mode": input_mode,
        "meta": {
            "available_slots": [
                {"index": k, "segment_id": v} for k, v in mapping.items()
            ]
        }
    }
    try:
        supabase.table("conversations").insert(payload).execute()
        print(f"[SLOT MAP SAVED] Mapping written for session {session_id}")
    except Exception as e:
        print(f"[SLOT MAP ERROR] Failed to save mapping: {e}")


def update_task_state(session_id: str, task_id: str | None):
    """
    Update the task status (task_id) of the latest record in the specified session
    """
    try:
        resp = supabase.table("conversations") \
            .select("id") \
            .eq("session_id", session_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        if not resp.data or len(resp.data) == 0:
            print(f"[TASK STATE] No conversation found for session={session_id}, skipping update.")
            return

        latest_id = resp.data[0]["id"]

        supabase.table("conversations") \
            .update({ "task_id": task_id }) \
            .eq("id", latest_id) \
            .execute()

    except Exception as e:
        print(f"[TASK STATE ERROR] Failed to update task for session {session_id}: {e}")


def get_session_task(session_id: str) -> str | None:
    """
    Get the task_id of the most recent round of the session for LLM prompt
    """
    try:
        res = supabase.table("conversations") \
            .select("task_id") \
            .eq("session_id", session_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if res.data and res.data[0].get("task_id"):
            return res.data[0]["task_id"]
    except Exception as e:
        print(f"[TASK STATE ERROR] Failed to fetch task_id for session {session_id}: {e}")
    return None



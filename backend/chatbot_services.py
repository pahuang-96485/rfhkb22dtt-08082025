#chatbot_services.py
from datetime import datetime, timezone, timedelta
from dateutil import parser
from dateutil.parser import parse as parse_date
from llm_client import call_llm_json, call_llm
import pytz
from zoneinfo import ZoneInfo
import random

from supabase_utils import (
    get_doctor_appointments,
    get_patient_appointments,
    get_doctor_schedule,
    cancel_appointment,
    reactivate_time_segment,
    book_slot,
    create_doctor_event,
    cancel_event,
    get_memory_history,
    get_available_segments,
    get_family_doctor,
    save_slot_mapping,
    get_family_doctor_id,
    get_session_task,
    update_task_state,
    find_matching_appointments,
    slot_matches_time_with_tz,
    find_matching_events
)


def get_user_tz(context: dict) -> ZoneInfo:
    tz_str = context.get("timezone", "UTC")
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("UTC") 


def is_exact_time_string(s: str) -> bool:
    try:
        datetime.strptime(s, "%H:%M")
        return True
    except Exception:
        return False


def run_llm_extract_intent(
    message: str,
    session_id: str,
    user: dict,
    context: dict | None = None,
    system_prompt: str | None = None,
    history_override: list[dict] | None = None
):

    user_tz = get_user_tz(context)
    today_iso = datetime.now().strftime("%Y-%m-%d")
    user_role = user["role"]
    task_id = get_session_task(session_id)
    
    history = history_override if history_override is not None else get_memory_history(session_id, limit=6)

    if system_prompt is None:
        system_prompt = f"""
        --- SYSTEM CONTEXT ---
        You are a helpful clinical assistant inside a real Clinical Decision Support System (CDSS).
        The current user is a **{user_role}**.
        Today is **{today_iso}**, and the user's local timezone is **{user_tz}**.
        Current task: **{task_id or None}**. Unless the user explicitly changes tasks, continue on this one. 
                
        --- PRIMARY GOAL ---
        Understand the user's intention and return **a single JSON block** in the following format:

        --- SUPPORTED ACTIONS ---
        a. book_appointment
        → Use one of:
        - args: {{ slot_index, description }}       ← if user picked from a numbered slot list
        - args: {{ preferred_date, preferred_time, days_ahead}}
        - Always convert relative time expressions (e.g. “tomorrow afternoon”, “next Tuesday”) into: preferred_date: YYYY-MM-DD based on {today_iso}
        - If the user says something like "next week", return:
        {{ "preferred_date": <Monday of next week>, "preferred_time": "any", "days_ahead": 7 }}
        - If user says something vague (e.g., "book an appointment for me"), return:
       {{ "preferred_date": "", "preferred_time": "any", "days_ahead": 7 }}



        b. cancel_appointment
        → args: {{ target, target_date (optional) }}
        - target: "next" → if user says "cancel my next appointment"
        - target: "date" + target_date (ISO format) → if user says "cancel the appointment on July 23"

        c. show_appointments
        → args: optionally include {{ from_date, to_date }}
        - Default: all future appointments (for patients)
        - Default: next 7 days (for doctors)

        d. show_my_schedule
        → args: {{ start_date (optional), days_ahead (optional) }}

        e. reactivate_time_segment
        → args: {{ slot_time }} ← use ISO format like "2025-07-27T13:00"
        - Only use this if the doctor said something like "reopen 1 PM on July 27"
        - If user says something vague (e.g., "reopen my blocked slots"), return:
        {{ "slot_time": "" }}
        and the system will prompt the user to clarify the date/time.

        f. reschedule_appointment
        → args: {{ target, target_date, preferred_date, preferred_time }}
        - If the user didn’t mention which appointment to reschedule, return target="next"
        - If user said a vague thing like “reschedule my appointment”, return:
        {{ "target": "next", "preferred_date": "", "preferred_time": "" }}
        and the system will ask follow-up questions to complete booking.

        g. create_event
        → args: {{ preferred_date, preferred_time, description }}
        - If user said a vague thing like “reschedule my appointment”, return:
        {{"preferred_date": "", "preferred_time": "" , "description":"" }}
        and the system will ask follow-up questions to complete booking.

        h. cancel_event
        → args: {{ preferred_date, preferred_time }}
        - If the user didn’t specify which event, but said "cancel my events", return:
        {{ "target_date": "", "time_pref": "" }}
        The system will follow up asking:
            “Which event would you like to cancel? Please mention the date or time.

        i. general_chat
        → {{ type: intro | help | empty }} ← e.g., when user says what can you do, thanks, etc.

        ---

        --- TIME & DATE ARGUMENTS (Unified Rule) ---
        For all tasks involving time:
        - Always convert relative time expressions (e.g. “tomorrow afternoon”, “next Tuesday”) into:
            - `preferred_date` → YYYY-MM-DD
            - `preferred_time` → "morning", "afternoon", "evening" or "14:00" if precise time provided
        - If the user didn’t provide enough information:
            → Leave the time/date fields empty.
            → Let the system follow up.


        --- SLOT SELECTION RULES ---
        - When presenting available_slots to the user:
        - Always format them as a clear numbered list:
            The soonest available slots with Your Family Doctor:
            1. 2025-07-20 14:00  
            2. 2025-07-20 14:30  
            3. 2025-07-20 15:00  
            ...
        - Do **not** summarize slots into time ranges like “from 2:00 PM to 4:30 PM”.
        - If the user selects a numbered slot (e.g., "I’ll pick 1" or "Option 3"), always return the `slot_index` 
        - If available_slots were presented in the previous turn, and the user now responds with a slot number or time, assume it’s a confirmation (slot_index), not a new search.
        - If a booking was already confirmed, do NOT repeat the slot search.


        ---

        --- EXAMPLES ---
        User: "Can I book the earliest available slot with my doctor?"
        → {{ 'action': 'book_appointment', 'arguments': {{ 'preferred_date': {today_iso}, 'preferred_time': 'any' }} }}

        User: "Cancel my next appointment"
        → {{ 'action': 'cancel_appointment', 'arguments': {{ 'target': 'next' }} }}

        User: "Schedule an event for July 25 in the afternoon"
        → {{ 'action': 'create_event', 'arguments': {{ 'preferred_date': '2025-07-25', 'preferred_time': 'afternoon', 'description': '' }} }}

        User: "Help"
        → {{ 'action': 'general_chat', 'arguments': {{ 'type': 'help' }} }}


        ---

        --- SAFETY RULES ---
        - Do NOT ask for login, password, or email.
        - Do NOT hallucinate names, IDs, or doctor information.
        - Do NOT return multiple actions or partial code.

        --- OUTPUT FORMAT (ALWAYS JSON) ---
        {{
        "action": "<action_string>", 
        "arguments": {{ ...all required fields for this action, even if empty }}
        }}

        - Always include the `"arguments"` key, even if some fields are unknown.
        - Never omit `"arguments"`.
        - If unsure about a field, return it as an empty string.
        """

    llm_input = history + [{"role": "user", "content": message}]
    result = call_llm_json(messages=llm_input, system_prompt=system_prompt)
    # print("RAW LLM INTENT CALL RESULT:", result)
    # print("RAW TOOL CALL EXTRACT:", json.dumps(result, indent=2))
    return result, ""


def run_llm_natural_reply(
    message: str,
    session_id: str,
    user: dict,
    context: dict | None = None,
    system_prompt: str | None = None,
    history_override: list[dict] | None = None
):

    #user_tz = get_user_tz(context)
    #today_iso = datetime.now().strftime("%Y-%m-%d")
    user_role = user["role"]

    history = history_override if history_override is not None else get_memory_history(session_id, limit=6)

    if system_prompt is None:
        system_prompt = f"""
        You are a helpful clinical assistant inside a scheduling system.

        The current user is a **{user_role}**.

        You will be given:
        - the user's original request
        - and a structured JSON output from the system (such as slot availability, booking status, etc.)

        Your task is to:
        - summarize the result in natural language
        - be concise (≤50 words), polite, and user-friendly
        - do NOT show any internal IDs or JSON keys
        """

    llm_input = history + [{"role": "user", "content": message}]
    return call_llm(messages=llm_input, system_prompt=system_prompt)


def build_search_explanation(preferred_date, preferred_time, days_ahead, user_tz, input_mode):

    parts = []
    mode_str = "voice" if input_mode == "voice" else "text"

    # Time preference 
    if preferred_time and preferred_time.lower() != "any":
        parts.append(f"I looked for {preferred_time} times")
    elif preferred_time and preferred_time.lower() == "any":
        parts.append("You didn’t specify a time of day, so I looked across all times")

    # Date/Range preference
    if preferred_date:
        # preferred_date is in format of YYYY-MM-DD
        try:
            local_dt = parser.parse(preferred_date).astimezone(user_tz)
            date_str = local_dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = preferred_date
        parts.append(f"starting on {date_str}")
        if days_ahead and days_ahead > 0:
            parts.append(f"and the next {days_ahead} day(s)")
    else:
        # No date given → use the earliest available date from the days_ahead range
        window = days_ahead if days_ahead and days_ahead > 0 else 7
        parts.append(f"for the earliest openings in the next {window} day(s)")

    sentence = " ".join(parts)

    if sentence and not sentence.endswith("."):
        sentence += "."
    return sentence



#######################
###Prompted Actions####
#######################

def handle_book_appointment(args, user, context: dict):
    print(f"[DEBUG] context passed in: {context}")
    print("[DEBUG] Booking args received by handle_book_appointment:", args)

    patient_id = user["id"]
    session_id = context.get("session_id")
    input_mode = context.get("input_mode", "text")
    user_tz = context.get("timezone_obj") if isinstance(context.get("timezone_obj"), timezone) else None
    # Fallback: if no explicit tz object is provided, use the local
    try:
        user_tz = user_tz or datetime.now().astimezone().tzinfo
    except Exception:
        user_tz = timezone.utc

    description = args.get("description", "")
    slot_index = args.get("slot_index")
    preferred_date = args.get("preferred_date")  
    preferred_time = args.get("preferred_time")
    days_ahead = int(args.get("days_ahead") or 0)

    # Step 1: Try direct booking via slot_index → segment_id mapping
    if slot_index and session_id:
        try:
            slot_index = int(slot_index)
            mapping = context.get("slot_mapping") or {}
            time_segment_id = mapping.get(slot_index)
            print(f"[DEBUG] Resolved slot_index={slot_index} → segment_id={time_segment_id}")
            if not time_segment_id:
                return {"reply": f"I couldn't find slot {slot_index}. Please try again.", "available_slots": []}

            appt = book_slot(patient_id, time_segment_id, description)
            print(f"[DEBUG] Booking succeeded: {appt}")

            doc_info = get_family_doctor(patient_id)
            fname = doc_info.get("fname", "").strip()
            lname = doc_info.get("lname", "").strip()
            doc_name = f"Dr. {fname} {lname}".strip() if fname or lname else "your doctor"

            local_time = parser.parse(appt["appointment_time"]).astimezone(user_tz).strftime("%Y-%m-%d at %H:%M %Z")

            if session_id:
                update_task_state(session_id, None)

            return {
                "reply": f"Your appointment with {doc_name} has been successfully booked for {local_time}.",
                "appointment": appt
            }

        except Exception as e:
            print(f"[ERROR] Booking failed: {str(e)}")
            return {"reply": "That time slot has just been taken. Please choose another.", "available_slots": []}

    # Step 2: Search by preferred date/time with fallbacks
    slots = []
    doc_info = get_family_doctor(patient_id)
    fname = doc_info.get("fname", "").strip()
    lname = doc_info.get("lname", "").strip()
    doc_name = f"Dr. {fname} {lname}".strip() if fname or lname else "your doctor"

    explanation = build_search_explanation(preferred_date, preferred_time, days_ahead, user_tz, input_mode)

    unavailable_notice = ""
    fallback_notice = ""

    # Allow preferred_date to be empty but search even when preferred_time/skylight exists
    if (preferred_date is not None) or preferred_time or days_ahead:
        # 2a: Preferred search (respects preferred_date, if empty, uses get_available_segments to search the earliest available segment in the world + days_ahead window)
        slots = get_available_segments(
            preferred_date=preferred_date or None,
            preferred_time=preferred_time,
            topn=5,
            user=user,
            days_ahead=days_ahead
        )

        # 2b: If a specific date is given but there is no number on that day → give alternatives for the next few days
        if preferred_date and not any(s["start_time"].startswith(preferred_date) for s in slots):
            unavailable_notice = f"Unfortunately, {doc_name} has no available slots on {preferred_date}. "
            try:
                dt = parser.parse(preferred_date)
                days_to_check = days_ahead if days_ahead > 0 else 5
                week_dates = [
                    (dt + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range(1, days_to_check + 1)
                ]
                for date in week_dates:
                    wk_slots = get_available_segments(
                        preferred_date=date,
                        preferred_time=preferred_time,
                        topn=5,
                        user=user,
                        days_ahead=days_to_check
                    )
                    if wk_slots:
                        fallback_notice = "Here are some options later next week: "
                        slots = wk_slots
                        print(f"[DEBUG] wk_slots found on {date}: {wk_slots}")
                        break
            except Exception as e:
                print(f"[FALLBACK ERROR] Failed to search future days: {e}")

        # 2c: If not → give the global earliest
        if not slots:
            slots = get_available_segments(
                preferred_time=preferred_time,
                topn=5,
                user=user
            )
            if slots:
                fallback_notice = "Here are the earliest options I could find: "

        if slots:
            for idx, s in enumerate(slots):
                s["index"] = idx + 1

            lines = [
                f"{s['index']}. {parser.parse(s['start_time']).astimezone(user_tz).strftime('%Y-%m-%d %H:%M %Z')}"
                for s in slots
            ]

            
            reply_parts = []
            if explanation:
                reply_parts.append(explanation)
            if unavailable_notice:
                reply_parts.append(unavailable_notice)
            if fallback_notice:
                reply_parts.append(fallback_notice)
            reply_parts.append("\n".join(lines))
            reply_parts.append("\nPlease respond with the number of your chosen slot.")

            reply = "\n".join([p for p in reply_parts if p])  
            print("[DEBUG] reply:", reply)

            if session_id:
                try:
                    save_slot_mapping(
                        session_id=session_id,
                        mapping={s["index"]: s["id"] for s in slots},
                        patient_id=patient_id,
                        doctor_id=get_family_doctor_id(patient_id),
                        role=user["role"],
                        input_mode=input_mode
                    )
                except Exception as e:
                    print(f"[SLOT MAP ERROR] Failed to save mapping: {e}")

            return {"reply": reply, "available_slots": slots}

    # Step 3: Total failure
    print("[DEBUG] No usable slot info found in args.")
    return {
        "reply": "I couldn't find any available appointments. Please provide a preferred time or try again later.",
        "available_slots": []
    }


def handle_cancel_appointment(args: dict, user: dict, context: dict = {}) -> dict:

    role = user["role"]
    user_id = user["id"]
    target = args.get("target")
    target_date = args.get("target_date")

    print(f"[DEBUG] Cancel request by {role} {user_id}, target={target}, date={target_date}")

    # 1. Query matching appointments
    matches = find_matching_appointments(
        role=role,
        user_id=user_id,
        target=target,
        target_date=target_date
    )
    print(f"[DEBUG] Raw matching appointments: {matches}")
    if not matches:
        print("[CANCEL] No matching appointment found.")
        return {
            "error": "not_found",
            "reason": "No matching appointment found."
        }

    # 2. Choose the earliest appointment
    
    appt = sorted(matches, key=lambda x: x["appointment_time"])[0]
    appointment_id = appt["appointment_id"]


    # 3. Execution cancellation (initiated by doctor or patient)

    result, err = cancel_appointment(appointment_id, by_doctor=(role == "doctor"))

    if err:
        print(f"[CANCEL ERROR] Failed to cancel: {err}")
        return {
            "error": err,
            "appointment_id": appointment_id,
            "reason": {
                "CANCEL_APPOINTMENT_NOT_FOUND": "Appointment not found or already cancelled.",
                "INTERNAL_CANCEL_ERROR": "Internal cancellation error."
            }.get(err, "Unknown error during cancellation.")
        }
 
    update_task_state(context.get("session_id"), None)

    # 4. Returns structured success information
    return {
        "appointment_id": appointment_id,
        "cancelled_time": appt["appointment_time"],
        "status": "cancelled"
    }


def handle_reschedule(args: dict, user: dict, context: dict = {}) -> dict:
    """
    Cancels the user's upcoming appointment (next or by date) and returns structured response.
    If successful, also triggers a rebooking process using preferred time.
    """
    

    target = args.get("target")               # "next" or "date"
    target_date = args.get("target_date")     # optional: ISO 8601
    preferred_date = args.get("preferred_date")
    preferred_time = args.get("preferred_time")
    session_id = context.get("session_id")
    user_tz = get_user_tz(context)
    

    print(f"[DEBUG] Reschedule requested by user {user['id']} → target={target}, date={target_date}, preferred={preferred_date} {preferred_time}")

    # 1. Find currently cancelable appointments
    matches = find_matching_appointments(
        user_id=user["id"],
        role=user["role"],
        target=target,
        target_date=target_date
    )

    if not matches:
        return {
            "reply": "You don’t have any upcoming appointments to reschedule.",
            "status": "not_found"
        }

    appt = sorted(matches, key=lambda x: x["appointment_time"])[0]
    appointment_id = appt["appointment_id"]
    appt_time = appt["appointment_time"]
    local_time = parse_date(appt_time).astimezone(user_tz).strftime("%Y-%m-%d %H:%M")

    print(f"[DEBUG] Found appointment to cancel → id={appointment_id}, time={appt_time}")

    # 2. Try to cancel
    result, err = cancel_appointment(appointment_id, by_doctor=(user["role"] == "doctor"))
    if err:
        msg = {
            "CANCEL_APPOINTMENT_NOT_FOUND": "Appointment not found or already cancelled.",
            "INTERNAL_CANCEL_ERROR": "Failed to cancel appointment (internal error)."
        }.get(err, f"Failed to cancel appointment: {err}")
        return { "reply": msg, "status": "cancel_failed" }

    # 3. Update the task status to reschedule
    update_task_state(session_id, "BOOK_APPT")

    # 4. Returns structured information (the summary prompt will continue processing)
    return {
        "reply": None,
        "status": "success",
        "cancelled_appointment": {
            "appointment_id": appointment_id,
            "original_time": local_time,
        },
        "next_step": "book_appointment",
        "preferred_date": preferred_date,
        "preferred_time": preferred_time
    }


def handle_show_appointments(args: dict, user: dict, context: dict = {}) -> dict:

    is_patient = user["role"] == "patient"
    user_id = user["id"]
    user_tz = get_user_tz(context)
    now = datetime.now(timezone.utc)


    if args.get("from_date"):
        from_date = parse_date(args["from_date"]).astimezone(timezone.utc)
    elif is_patient:
        from_date = now - timedelta(days=1)  # Default patient to see all future appointments
    else:
        from_date = now  # Doctors default to check from today

    if args.get("to_date"):
        to_date = parse_date(args["to_date"]).astimezone(timezone.utc)
    elif is_patient:
        to_date = now + timedelta(days=90)  # Patients can check for the next 3 months at most
    else:
        to_date = now + timedelta(days=7)   # Doctors only check the next 7 days by default

    print(f"[DEBUG] show_appointments: from={from_date.date()} to={to_date.date()}")

    appts = get_patient_appointments(user_id) if is_patient else get_doctor_appointments(user_id)
    result = []

    for a in appts.data:
        try:
            dt_utc = parse_date(a["appointment_time"]).astimezone(timezone.utc)
            if a.get("status") != 1:
                continue
            if not (from_date <= dt_utc <= to_date):
                continue

            local_time = dt_utc.astimezone(user_tz)

            if is_patient:
                doc = a.get("doctors_registration", {})
                name = f"Dr. {doc.get('fname', '').strip()} {doc.get('lname', '').strip()}"
            else:
                pat = a.get("patients_registration", {})
                name = f"{pat.get('fname', '').strip()} {pat.get('lname', '').strip()}"

            result.append({
                "appointment_id": a.get("appointment_id"),
                "local_time": local_time.strftime("%Y-%m-%d %H:%M"),
                "name": name.strip()
            })

        except Exception as e:
            print(f"[WARN] Skipping invalid appointment: {e}")
            continue


    if not result:
        return { "reply": "You don’t have any upcoming appointments.", "appointments": [] }

    update_task_state(context.get("session_id"), None)

    return {
        "reply": f"You have {len(result)} upcoming appointment(s).",
        "appointments": result
    }


#Doctor Only
def handle_doctor_schedule(args: dict, user: dict, context: dict = {}) -> dict:
    
    if user.get("role") != "doctor":
        return {"reply": "Only doctors can view schedules."}

    doctor_id = user["id"]
    tz = pytz.timezone(user.get("timezone", "UTC"))
    start_date = args.get("target_date")
    days_ahead = args.get("days_ahead")

    if not start_date and days_ahead:
        today = datetime.now(tz).date()
        start_date = today.isoformat()
        end_date = (today + timedelta(days=int(days_ahead))).isoformat()
    else:
        end_date = None

    segments = get_doctor_schedule(doctor_id, start_date=start_date, end_date=end_date)

    if not segments:
        return {"reply": "No available schedule found.", "slots": []}
    
    update_task_state(context.get("session_id"), None)

    return {
        "reply": f"Schedule from {start_date or 'today'}" + (f" to {end_date}" if end_date else ""),
        "slots": segments
    }


#Doctor Only
def handle_reactivate(args: dict, user: dict, context: dict = {}) -> dict:


    if user.get("role") != "doctor":
        return {"error": "Only doctors can reactivate segments."}

    slot_time_str = args.get("slot_time")
    if not slot_time_str:
        return {"reply": "Please tell me the time you want to reopen (e.g. '5:30 PM on July 27')."}

    try:
        slot_dt = parse_date(slot_time_str).astimezone(timezone.utc)
    except Exception:
        return {"reply": "Sorry, I couldn't understand the time. Could you rephrase it?"}

    # Fetch full schedule
    segments = get_doctor_schedule(user["id"])
    print(f"[DEBUG] Reactivate slot: looking for segment at {slot_dt.isoformat()}")

    for seg in segments:
        seg_time = parse_date(seg["start_time"]).astimezone(timezone.utc)
        if seg["status"] == -1 and abs((slot_dt - seg_time).total_seconds()) < 60:
            segment_id = seg["segment_id"]

            try:
                reactivate_time_segment(segment_id)
                update_task_state(context.get("session_id"), None)
                return {
                    "reply": f" Segment at {seg_time.strftime('%Y-%m-%d %H:%M')} reactivated.",
                    "segment_id": segment_id
                }
            except ValueError as ve:
                return { "reply": f"Reactivate failed: {str(ve)}" }

    return { "reply": f"No blocked segment found at {slot_dt.strftime('%Y-%m-%d %H:%M')}. Please try another time." }


#Doctor Only
def handle_create_event(args: dict, user: dict, context: dict = {}) -> dict:

    if user.get("role") != "doctor":
        return {"error": "Only doctors can create events."}

    doctor_id = user["id"]
    description = args.get("description") or args.get("title") or "Event"
    preferred_date = args.get("preferred_date")
    preferred_time = args.get("preferred_time")  # e.g. "14:00" or "afternoon"
    user_tz = get_user_tz(context)

    if not preferred_date:
        return {"reply": "Please tell me which date you'd like to block.", "event_created": False}

    slots = get_doctor_schedule(doctor_id, start_date=preferred_date, end_date=preferred_date)
    candidate = None

    print(f"[DEBUG] Found {len(slots)} segments on {preferred_date}")

    # Step 1: Exact time match (if preferred_time is "HH:MM")
    if preferred_time and is_exact_time_string(preferred_time):
        target_hour, target_minute = map(int, preferred_time.split(":"))
        for s in slots:
            dt_local = parse_date(s["start_time"]).astimezone(user_tz)
            print(f"[DEBUG] Checking segment {s['segment_id']} at {dt_local} → status={s['status']}")
            if s["status"] == 0 and dt_local.hour == target_hour and dt_local.minute == target_minute:
                candidate = s
                break

    # Step 2: Fallback to divisions of the day (morning/afternoon/evening)
    if not candidate and preferred_time:
        for s in slots:
            dt_local = parse_date(s["start_time"]).astimezone(user_tz)
            match = slot_matches_time_with_tz(dt_local, preferred_time, user_tz)
            print(f"[DEBUG] Fallback check: segment {s['segment_id']} at {dt_local} → match_time_pref={match}")
            if s["status"] == 0 and match:
                candidate = s
                break

    if not candidate:
        return {"reply": "No available time slot found on that date.", "event_created": False}

    segment_id = candidate["segment_id"]
    print(f"[DEBUG] Selected segment: {segment_id} ({candidate['start_time']})")

    result, err = create_doctor_event(segment_id, doctor_id, description)

    if err == "EVENT_SEGMENT_NOT_AVAILABLE":
        return {"reply": "That slot is already taken. Please choose another.", "event_created": False}
    elif err:
        return {"reply": f"Failed to create event: {err}", "event_created": False}

    update_task_state(context.get("session_id"), None)

    return {
        "reply": f"Got it. I've scheduled the event: **{description}** at {candidate['start_time']}.",
        "segment_id": segment_id,
        "event_created": True
    }


#Doctor Only
def handle_cancel_event(args: dict, user: dict, context: dict = {}) -> dict:

 
    if user.get("role") != "doctor":
        return {"error": "Only doctors can cancel events."}

    doctor_id = user["id"]
    user_tz = get_user_tz(context)
    print("user_tz: ", user_tz)

    preferred_date = args.get("preferred_date")
    preferred_time = args.get("preferred_time") or args.get("time_pref")

    print(f"[DEBUG] handle_cancel_event input: preferred_date={preferred_date}, time={preferred_time}, doctor={doctor_id}")

    if not preferred_date or not preferred_time:
        return {"error": "Please specify the date and time of the event you want to cancel."}

    matches = find_matching_events(
        doctor_id=doctor_id,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        user_tz=user_tz
    )
    print(f"[DEBUG] Found matching events: {matches}")

    if not matches:
        return {"error": "No matching event found."}

    event = sorted(matches, key=lambda x: x["start_time"])[0]
    segment_id = event["segment_id"]

    segment_time, err = cancel_event(segment_id=segment_id, doctor_id=doctor_id)

    if err:
        print(f"[ERROR] Cancel failed: {err}")
        return {"error": "Failed to cancel the event.", "reason": err}

    update_task_state(context.get("session_id"), None)

    try:
        local_time = parse_date(segment_time).astimezone(pytz.timezone(user_tz))
        formatted = local_time.strftime('%Y-%m-%d %H:%M')
    except Exception:
        formatted = segment_time

    return {
        "reply": f"Event on {formatted} cancelled.",
        "segment_time": segment_time,
        "event_cancelled": True
    }


def handle_action_dispatch(extracted: dict, user: dict, context: dict = {}) -> str | dict:
    
    ACTION_MAP = {
        "a": "book_appointment",
        "b": "cancel_appointment",
        "c": "show_appointments",
        "d": "show_my_schedule",
        "e": "reactivate_time_segment",
        "f": "reschedule_appointment",
        "g": "create_event",
        "h": "cancel_event",
    }
    action = extracted.get("action")
    if action in ACTION_MAP:
        action = ACTION_MAP[action]

    session_id = context.get("session_id")
    if session_id and action:
        task_enum_map = {
            "book_appointment": "BOOK_APPT",
            "cancel_appointment": "CANCEL_APPT",
            "show_appointments": "SHOW_APPT",
            "show_my_schedule": "SHOW_SCHEDULE",
            "reactivate_time_segment": "REACTIVATE_SEGMENT",
            "reschedule_appointment": "RESCHEDULE_APPT",
            "create_event": "CREATE_EVENT",
            "cancel_event": "CANCEL_EVENT"
        }
        task_id = task_enum_map.get(action)

        if task_id:
            update_task_state(session_id, task_id)


    if action == "book_appointment":
        return handle_book_appointment(extracted["arguments"], user, context)
    elif action == "cancel_appointment":
        return handle_cancel_appointment(extracted["arguments"], user, context)
    elif action == "show_appointments":
        return handle_show_appointments(extracted["arguments"], user, context)
    elif action == "show_my_schedule":
        return handle_doctor_schedule(extracted["arguments"], user, context)
    elif action == "reactivate_time_segment":
        return handle_reactivate(extracted["arguments"], user, context)
    elif action == "reschedule_appointment":
        return handle_reschedule(extracted["arguments"], user, context)
    elif action == "create_event":
        return handle_create_event(extracted["arguments"], user, context)
    elif action == "cancel_event":
        return handle_cancel_event(extracted["arguments"], user, context)
    elif action == "general_chat":
        chat_type = extracted.get("arguments", {}).get("type", "")
        if chat_type == "intro":
            return {"reply": "Hi! I'm your scheduling assistant. I can help you book, cancel, or view appointments."}
        elif chat_type == "help":
            return {"reply": "You can say things like 'Book me an appointment tomorrow morning' or 'Cancel my next appointment'."}
        else:
            return {"reply": random.choice([
                "Let me know if you need help with anything else.",
                "Got it. I'm here if you need me."
            ])}
    return {
    "error": "unsupported_action",
    "reply": "Sorry, I couldn't understand your request. Can you rephrase?"
    }





#main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json

from supabase_utils import (
    log_conversation, 
    delete_conversations, 
    get_memory_history
)

from supabase_utils import (
    register_doctor_user,
    register_patient_user,
    get_user_info_by_email,
    auth_dependency,
    login_user,
    get_user_by_uuid_and_role,
    get_session_task,
    get_slot_mapping
)

from chatbot_services import (
    run_llm_extract_intent,
    run_llm_natural_reply,
    handle_action_dispatch
)


app = FastAPI()


# Allow React frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Schemas
class DoctorRegisterRequest(BaseModel):
    fname: str
    lname: str
    emailid: str
    mobilenumber: str
    location1 : str
    city: str
    province: str
    country: str
    medical_license_number: str
    specialization: str
    password: str

class PatientRegisterRequest(BaseModel):
    fname: str
    lname: str
    emailid: str
    mobilenumber: str
    city: str
    province: str
    address: str
    password: str



class RegisterRequest(BaseModel):
    emailid: str
    password: str
    nickname: str
    role: str  # 'patient' or 'doctor'

class ChatRequest(BaseModel):
    message: str               
    context: Optional[dict]    

class LoginRequest(BaseModel):
    emailid:    str
    password: str

class LogoutRequest(BaseModel):
    session_id: str


################User registration and login################
@app.post("/register/doctor")
def register_doctor(req: DoctorRegisterRequest):
    return register_doctor_user(req)

@app.post("/register/patient")
def register_patient(req: PatientRegisterRequest):
    return register_patient_user(req)


@app.post("/login")
def login(req: LoginRequest):
    data, err = login_user(req.emailid, req.password)
    if err:
        raise HTTPException(status_code=401, detail=err)
    return data

@app.post("/logout")
def logout(req: LogoutRequest):
    delete_conversations(req.session_id)
    return {"ok": True}


@app.get("/user")
def get_user(emailid: str, role: str):
    user = get_user_info_by_email(emailid, role)
    if user:
        return user
    return {"error": "User not found"}, 404


################ChatBot################

def clean_history_for_llm(history: list[dict]) -> list[dict]:
    cleaned = []
    for h in history:
        role = h.get("role", "")
        if role not in ("user", "assistant", "system", "tool"):
            role = "user"
        cleaned.append({ "role": role, "content": h["content"] })
    return cleaned

@app.middleware("http")
async def log_requests(request: ChatRequest, call_next):
    print(f"→ Incoming: {request.method} {request.url.path}")
    response = await call_next(request)
    print(f"← Outgoing: {response.status_code}")
    return response

@app.post("/chat/voice")
def handle_voice(req: ChatRequest, user=Depends(auth_dependency)):
    print(f"[VOICE] Explicit voice endpoint called: {req.message}")
    return chat_endpoint(req, user)  

@app.post("/chat/text")
def handle_text(req: ChatRequest, user=Depends(auth_dependency)):
    print(f"[TEXT] Explicit text endpoint called: {req.message}")
    return chat_endpoint(req, user)


def chat_endpoint(req: ChatRequest, user=Depends(auth_dependency)):


    # 0. Extracting the context field
    context = req.context or {}
    session_id = context.get("session_id")
    input_mode = context.get("input_mode")
    role = user["role"]  

    # 1. Get complete user information
    db_user = get_user_by_uuid_and_role(user["uuid"], role)
    if not db_user:
        return {"reply": "Error: No user context found."}

    full_user = {
        "id": db_user["id"],
        "uuid": db_user["uuid"],
        "role": role,
        "fname": db_user.get("fname", ""),
        "lname": db_user.get("lname", ""),
        "emailid": db_user.get("emailid", "")
    }
    # Debug: Print basic information of the received request


    # 2. Get the historical memory and add the user's current input
    history = get_memory_history(session_id, limit=6)
    history.append({"role": "user", "content": req.message})

    # 3. First round of LLM: Structured Intent Recognition
    extracted, _ = run_llm_extract_intent(
        message=req.message,
        session_id=session_id,
        user=full_user,
        context=context,
        history_override=history
    )

    print(f"[First LLM intend Extracted] {extracted}")
    # Preload the slot_index → segment_id mapping in advance to avoid repeated queries
    slot_mapping = get_slot_mapping(session_id)
    context["slot_mapping"] = slot_mapping

    # 4. handler executes the task → returns the structure result
    routed_response = handle_action_dispatch(extracted, full_user, context=context or {})
    

    # 5. Construct the second round of summary prompts
    structured_summary = json.dumps(routed_response, ensure_ascii=False, indent=2) if isinstance(routed_response, dict) else str(routed_response)    
    # Get the current task_id status
    task_id = get_session_task(session_id)
    # Splice the natural language summary prompt to bring in the current task status
    summary_prompt = f"""
    [System Info]
    Current task: {task_id or "None"}.
    User asked: \"{req.message}\"
    System executed the action and returned this structured response:
    {structured_summary}

    Response Rules:  
    1. If 'available_slots' exists:
    - Repeat the exact text from the `reply` field as-is. Do NOT remove or rephrase it.
    - Do NOT try to re-list the slots or parse them yourself.
    - After the reply, append ONLY this sentence:  
    "Please respond with the number of your chosen slot." 

    2. Otherwise:  
    - Generate a short, polite, user-friendly natural language reply.

    Prohibited:  
    - Summarizing time ranges  
    - Adding extra explanations
    - Show any internal JSON, IDs, or keys
    - emojis/icons/special characters

    """

    # 5.1 If the system returns a slot list, it means the user has not selected yet, remind the LLM not to skip it
    if isinstance(routed_response, dict) and routed_response.get("available_slots"):
        summary_prompt += """
        Note: The system is currently waiting for the user to choose a slot_index from the list above.
        Do NOT assume the appointment has been booked.
        Just gently prompt the user to pick one option (e.g., "Please pick a number from the list").
        """

    # 6. Second round of LLM: Generating natural language
    final_reply = run_llm_natural_reply(
        message=summary_prompt,
        session_id=session_id,
        user=full_user,
        context=context,
        history_override=clean_history_for_llm(history)
    )

    print(f"[Second LLM natural_reply] {final_reply}")

    # 7. Try to get the ID from routed_response, allowing it to be empty
    if full_user["role"] == "patient":
        patient_id = full_user["id"]
        doctor_id = routed_response.get("doctor_id") if isinstance(routed_response, dict) else None
    else:  # full_user["role"] == "doctor"
        doctor_id = full_user["id"]
        patient_id = routed_response.get("patient_id") if isinstance(routed_response, dict) else None


    # 8. Write conversations (allow patient_id or doctor_id to be NULL)
    log_conversation(
        session_id=session_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        role=full_user["role"],
        input=req.message,
        response=final_reply,
        input_mode=input_mode,
        meta=routed_response if isinstance(routed_response, dict) else None
)


    # 9. Return to front end
    return {
        "reply": final_reply,
        "available_slots": routed_response.get("available_slots", []) if isinstance(routed_response, dict) else []
    }



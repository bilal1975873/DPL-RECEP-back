from ai_integration import AIReceptionist
from flows import guest_flow, SUPPLIERS, vendor_flow, validate_cnic, validate_phone
import asyncio

# --- FastAPI & MongoDB Integration ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Literal
from pymongo import MongoClient
from datetime import datetime, timezone
import os
import time

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["dpl_receptionist_db"]
visitors_collection = db["visitors"]

# Pydantic Visitor model
class Visitor(BaseModel):
    type: Literal['guest', 'vendor']
    full_name: str
    cnic: str
    phone: str
    host: str
    purpose: str
    entry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: Optional[datetime] = None
    is_group_visit: bool = False
    group_id: Optional[str] = None
    total_members: int = 1
    group_members: list = []

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/visitors/", response_model=Visitor)
def create_visitor(visitor: Visitor):
    data = visitor.dict()
    result = visitors_collection.insert_one(data)
    if not result.acknowledged:
        raise HTTPException(status_code=500, detail="Failed to insert visitor.")
    data["_id"] = str(result.inserted_id)
    return visitor

@app.get("/visitors/", response_model=list[Visitor])
def list_visitors():
    visitors = list(visitors_collection.find())
    for v in visitors:
        v.pop("_id", None)
    return visitors

@app.get("/visitors/{cnic}", response_model=Visitor)
def get_visitor(cnic: str):
    visitor = visitors_collection.find_one({"cnic": cnic})
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    visitor.pop("_id", None)
    return Visitor(**visitor)

@app.put("/visitors/{cnic}", response_model=Visitor)
def update_visitor(cnic: str, update: Visitor):
    result = visitors_collection.update_one({"cnic": cnic}, {"$set": update.dict()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    return update

@app.delete("/visitors/{cnic}")
def delete_visitor(cnic: str):
    result = visitors_collection.delete_one({"cnic": cnic})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    return {"detail": "Visitor deleted."}

def insert_visitor_to_db(visitor_type, full_name, cnic, phone, host, purpose, is_group_visit=False, group_members=None, total_members=1):
    entry_time = datetime.now(timezone.utc)
    group_id = None
    
    if is_group_visit:
        group_id = str(datetime.now(timezone.utc).timestamp())

    visitor_doc = {
        "type": visitor_type,
        "full_name": full_name,
        "cnic": cnic,
        "phone": phone,
        "host": host,
        "purpose": purpose,
        "entry_time": entry_time,
        "exit_time": None,
        "is_group_visit": is_group_visit,
        "group_id": group_id,
        "total_members": total_members,
        "group_members": group_members or []
    }
    visitors_collection.insert_one(visitor_doc)

class VisitorInfo:
    def __init__(self):
        self.visitor_type = None
        self.visitor_name = None
        self.visitor_cnic = None
        self.visitor_phone = None
        self.host_requested = None
        self.host_confirmed = None
        self.host_email = None
        self.purpose = None
        self.verification_status = None
        self.supplier = None  # For vendor flow
        self.group_id = None  # For group visits
        self.is_group_visit = False
        self.group_members = []  # List to store additional visitors
        self.total_members = 1  # Default to 1, will be updated for groups
        
    def to_dict(self):
        return {
            "visitor_type": self.visitor_type,
            "visitor_name": self.visitor_name,
            "visitor_cnic": self.visitor_cnic,
            "visitor_phone": self.visitor_phone,
            "host_requested": self.host_requested,
            "host_confirmed": self.host_confirmed,
            "host_email": self.host_email,
            "purpose": self.purpose,
            "verification_status": self.verification_status,
            "supplier": self.supplier,
            "group_id": self.group_id,
            "is_group_visit": self.is_group_visit,
            "total_members": self.total_members,
            "group_members": self.group_members
        }
    
    def summary(self):
        lines = ["=== Visitor Information Summary ==="]
        if self.visitor_name:
            lines.append(f"Name: {self.visitor_name}")
        if self.visitor_cnic:
            lines.append(f"CNIC: {self.visitor_cnic}")
        if self.visitor_phone:
            lines.append(f"Phone: {self.visitor_phone}")
        if self.host_confirmed:
            lines.append(f"Host: {self.host_confirmed}")
        if self.purpose:
            lines.append(f"Purpose: {self.purpose}")
        return "\n".join(lines)

class DPLReceptionist:
    def __init__(self):
        self.visitor_info = VisitorInfo()
        self.ai = AIReceptionist()
        self.current_step = "visitor_type"
        self.employee_selection_mode = False
        self.employee_matches = []
        
    def reset(self):
        self.__init__()
        
    async def process_input(self, user_input: str) -> str:
        # Handle visitor type selection (only at the very start)
        if self.current_step == "visitor_type":
            user_input = user_input.lower().strip()
            if user_input in ["1", "guest"]:
                self.visitor_info.visitor_type = "guest"
                self.current_step = "name"
            elif user_input in ["2", "vendor"]:
                self.visitor_info.visitor_type = "vendor"
                self.current_step = "supplier"
            elif user_input == "3":
                return "This feature is not yet implemented. Please select option 1 for guest or 2 for vendor registration."
            else:
                # Repeat the visitor type selection message if invalid
                return "Please select your visitor type: 1 for Guest, 2 for Vendor."
            context = {"current_step": self.current_step, **self.visitor_info.to_dict()}
            if self.current_step == "supplier":
                # Always show supplier list immediately
                supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                return f"Please select your supplier company:\n{supplier_list}"
            return await self.get_ai_response(user_input, context)

        # Employee selection mode (for host selection)
        if self.employee_selection_mode:
            if user_input.isdigit() and int(user_input) == 0:
                self.employee_selection_mode = False
                context = {"current_step": "host", **self.visitor_info.to_dict()}
                return await self.get_ai_response(user_input, context)
            elif user_input.isdigit() and 1 <= int(user_input) <= len(self.employee_matches):
                selected = self.employee_matches[int(user_input) - 1]
                self.visitor_info.host_confirmed = selected["displayName"]
                self.visitor_info.host_email = selected["email"]
                self.employee_selection_mode = False
                self.current_step = "purpose"
                context = {"current_step": "purpose", **self.visitor_info.to_dict()}
                return await self.get_ai_response(user_input, context)
            else:
                return "I found multiple potential matches. Please select one by number or 0 to enter a different name."

        # Guest flow (strict, only hardcoded prompts, strict step order)
        if self.visitor_info.visitor_type == "guest":
            steps = guest_flow["steps"]
            step_idx = steps.index(self.current_step) if self.current_step in steps else 0
            if self.current_step == "name":
                if not user_input.strip():
                    return "Please enter your name."
                self.visitor_info.visitor_name = user_input.strip()
                self.current_step = "group_size"
                return "Please provide the size of your group."
            elif self.current_step == "group_size":
                try:
                    group_size = int(user_input.strip())
                    if group_size < 1:
                        return "Please enter a valid group size (at least 1)."
                    if group_size > 10:
                        return "Maximum group size is 10 people. Please enter a smaller number."
                    self.visitor_info.total_members = group_size
                    self.visitor_info.is_group_visit = group_size > 1
                    if group_size > 1:
                        self.visitor_info.group_id = str(datetime.now(timezone.utc).timestamp())
                    self.current_step = "cnic"
                    return "Please provide your CNIC number in the format: 12345-1234567-1."
                except ValueError:
                    return "Please enter a valid group size (number)."
            elif self.current_step == "cnic":
                if not validate_cnic(user_input.strip()):
                    return "Please provide a valid CNIC number in the format: 12345-1234567-1."
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "phone"
                return "Please enter your phone number."
            elif self.current_step == "phone":
                if not validate_phone(user_input.strip()):
                    return "Please enter a valid phone number."
                self.visitor_info.visitor_phone = user_input.strip()
                # If group, start collecting group member info
                if self.visitor_info.is_group_visit and len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                    next_member = len(self.visitor_info.group_members) + 2
                    self.current_step = f"member_{next_member}_name"
                    return f"Please enter the name of group member {next_member}:"
                self.current_step = "host"
                return "Who are you visiting?"
            # Group member collection for guest
            elif self.current_step.startswith("member_"):
                parts = self.current_step.split("_")
                member_num = int(parts[1])
                substep = parts[2]
                if substep == "name":
                    self.visitor_info.group_members.append({"name": user_input.strip()})
                    self.current_step = f"member_{member_num}_cnic"
                    return f"Please enter the CNIC number of group member {member_num} (format: 12345-1234567-1):"
                elif substep == "cnic":
                    if not validate_cnic(user_input.strip()):
                        return f"Please provide a valid CNIC number for group member {member_num} in the format: 12345-1234567-1."
                    self.visitor_info.group_members[member_num-2]["cnic"] = user_input.strip()
                    self.current_step = f"member_{member_num}_phone"
                    return f"Please enter the phone number of group member {member_num}:"
                elif substep == "phone":
                    if not validate_phone(user_input.strip()):
                        return f"Please provide a valid phone number for group member {member_num}."
                    self.visitor_info.group_members[member_num-2]["phone"] = user_input.strip()
                    # If more members to collect
                    if len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                        next_member = len(self.visitor_info.group_members) + 2
                        self.current_step = f"member_{next_member}_name"
                        return f"Please enter the name of group member {next_member}:"
                    else:
                        self.current_step = "host"
                        return "Who are you visiting?"
            elif self.current_step == "host":
                employee = await self.ai.search_employee(user_input)
                if isinstance(employee, dict):
                    self.visitor_info.host_confirmed = employee["displayName"]
                    self.visitor_info.host_email = employee["email"]
                    self.current_step = "purpose"
                    return "Please provide the purpose of your visit."
                elif isinstance(employee, list):
                    self.employee_selection_mode = True
                    self.employee_matches = employee
                    options = "I found multiple potential matches. Please select one by number:\n"
                    for i, emp in enumerate(employee, 1):
                        dept = emp.get("department", "Unknown Department")
                        options += f"  {i}. {emp['displayName']} ({dept})\n"
                    options += "  0. None of these / Enter a different name"
                    return options
                else:
                    return "No matches found. Please enter a different name."
            elif self.current_step == "purpose":
                if not user_input.strip():
                    return "Please provide the purpose of your visit."
                self.visitor_info.purpose = user_input.strip()
                self.current_step = "confirm"
                # Always show summary for confirmation
                summary = f"Name: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                if self.visitor_info.is_group_visit:
                    summary += f"\nGroup size: {self.visitor_info.total_members}"
                    for idx, member in enumerate(self.visitor_info.group_members, 2):
                        summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                if self.visitor_info.host_confirmed:
                    summary += f"\nHost: {self.visitor_info.host_confirmed}"
                if self.visitor_info.purpose:
                    summary += f"\nPurpose: {self.visitor_info.purpose}"
                return f"Please review your information and type 'confirm' to proceed or 'edit' to make changes.\n{summary}"
            elif self.current_step == "confirm":
                if user_input.lower() == "confirm":
                    self.current_step = "complete"
                    insert_visitor_to_db(
                        visitor_type=self.visitor_info.visitor_type or "guest",
                        full_name=self.visitor_info.visitor_name or "",
                        cnic=self.visitor_info.visitor_cnic or "",
                        phone=self.visitor_info.visitor_phone or "",
                        host=self.visitor_info.host_confirmed or "",
                        purpose=self.visitor_info.purpose or "",
                        is_group_visit=self.visitor_info.is_group_visit,
                        group_members=self.visitor_info.group_members,
                        total_members=self.visitor_info.total_members
                    )
                    # Schedule meeting and notify host
                    try:
                        if self.ai.graph_client is not None:
                            await self.ai.schedule_meeting(
                                self.visitor_info.host_email,
                                self.visitor_info.visitor_name,
                                self.visitor_info.purpose
                            )
                    except Exception as e:
                        print(f"Error scheduling meeting: {e}")
                    return "Your registration is complete."
                elif user_input.lower() == "edit":
                    self.current_step = "name"
                    return "Please enter your name."
                else:
                    # Show summary for confirmation again
                    summary = f"Name: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                    if self.visitor_info.is_group_visit:
                        summary += f"\nGroup size: {self.visitor_info.total_members}"
                        for idx, member in enumerate(self.visitor_info.group_members, 2):
                            summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                    if self.visitor_info.host_confirmed:
                        summary += f"\nHost: {self.visitor_info.host_confirmed}"
                    if self.visitor_info.purpose:
                        summary += f"\nPurpose: {self.visitor_info.purpose}"
                    return f"Please review your information and type 'confirm' to proceed or 'edit' to make changes.\n{summary}"
            elif self.current_step == "complete":
                return "Your registration is complete."

        # Vendor flow (strict, only hardcoded prompts, strict step order)
        if self.visitor_info.visitor_type == "vendor":
            if self.current_step == "supplier":
                supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                if user_input.isdigit() and 1 <= int(user_input) <= len(SUPPLIERS):
                    selected = SUPPLIERS[int(user_input) - 1]
                    if selected == "Other":
                        self.current_step = "supplier_other"
                        return "Please enter your supplier company name."
                    else:
                        self.visitor_info.supplier = selected
                        self.current_step = "vendor_name"
                        return "Please enter your name."
                elif user_input.strip() in SUPPLIERS:
                    if user_input.strip() == "Other":
                        self.current_step = "supplier_other"
                        return "Please enter your supplier company name."
                    else:
                        self.visitor_info.supplier = user_input.strip()
                        self.current_step = "vendor_name"
                        return "Please enter your name."
                else:
                    return f"Please select your supplier company from the list below:\n{supplier_list}"
            elif self.current_step == "supplier_other":
                if user_input.strip():
                    self.visitor_info.supplier = user_input.strip()
                    self.current_step = "vendor_name"
                    return "Please enter your name."
                else:
                    return "Please enter your supplier company name."
            elif self.current_step == "vendor_name":
                if not user_input.strip():
                    return "Please enter your name."
                self.visitor_info.visitor_name = user_input.strip()
                self.current_step = "vendor_group_size"
                return "Please provide the size of your group."
            elif self.current_step == "vendor_group_size":
                try:
                    group_size = int(user_input.strip())
                    if group_size < 1:
                        return "Please enter a valid group size (at least 1)."
                    if group_size > 10:
                        return "Maximum group size is 10 people. Please enter a smaller number."
                    self.visitor_info.total_members = group_size
                    self.visitor_info.is_group_visit = group_size > 1
                    if group_size > 1:
                        self.visitor_info.group_id = str(datetime.now(timezone.utc).timestamp())
                    self.current_step = "vendor_cnic"
                    return "Please provide your CNIC number in the format: 12345-1234567-1."
                except ValueError:
                    return "Please enter a valid group size (number)."
            elif self.current_step == "vendor_cnic":
                if not validate_cnic(user_input.strip()):
                    return "Please provide a valid CNIC number in the format: 12345-1234567-1."
                self.visitor_info.visitor_cnic = user_input.strip()
                self.current_step = "vendor_phone"
                return "Please enter your phone number."
            elif self.current_step == "vendor_phone":
                if not validate_phone(user_input.strip()):
                    return "Please provide a valid phone number."
                self.visitor_info.visitor_phone = user_input.strip()
                # If group, start collecting group member info
                if self.visitor_info.is_group_visit and len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                    next_member = len(self.visitor_info.group_members) + 2
                    self.current_step = f"vendor_member_{next_member}_name"
                    return f"Please enter the name of vendor group member {next_member}:"
                self.current_step = "vendor_confirm"
                # Show summary for confirmation
                summary = f"Supplier: {self.visitor_info.supplier}\nName: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                if self.visitor_info.is_group_visit:
                    summary += f"\nGroup size: {self.visitor_info.total_members}"
                    for idx, member in enumerate(self.visitor_info.group_members, 2):
                        summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                return f"Please review your information and type 'yes' to confirm or 'no' to edit.\n{summary}"
            # Group member collection for vendor
            elif self.current_step.startswith("vendor_member_"):
                parts = self.current_step.split("_")
                member_num = int(parts[2])
                substep = parts[3]
                if substep == "name":
                    self.visitor_info.group_members.append({"name": user_input.strip()})
                    self.current_step = f"vendor_member_{member_num}_cnic"
                    return f"Please enter the CNIC number of vendor group member {member_num} (format: 12345-1234567-1):"
                elif substep == "cnic":
                    if not validate_cnic(user_input.strip()):
                        return f"Please provide a valid CNIC number for vendor group member {member_num} in the format: 12345-1234567-1."
                    self.visitor_info.group_members[member_num-2]["cnic"] = user_input.strip()
                    self.current_step = f"vendor_member_{member_num}_phone"
                    return f"Please enter the phone number of vendor group member {member_num}:"
                elif substep == "phone":
                    if not validate_phone(user_input.strip()):
                        return f"Please provide a valid phone number for vendor group member {member_num}."
                    self.visitor_info.group_members[member_num-2]["phone"] = user_input.strip()
                    # If more members to collect
                    if len(self.visitor_info.group_members) < self.visitor_info.total_members - 1:
                        next_member = len(self.visitor_info.group_members) + 2
                        self.current_step = f"vendor_member_{next_member}_name"
                        return f"Please enter the name of vendor group member {next_member}:"
                    else:
                        self.current_step = "vendor_confirm"
                        summary = f"Supplier: {self.visitor_info.supplier}\nName: {self.visitor_info.visitor_name}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                        if self.visitor_info.is_group_visit:
                            summary += f"\nGroup size: {self.visitor_info.total_members}"
                            for idx, member in enumerate(self.visitor_info.group_members, 2):
                                summary += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                        return f"Please review your information and type 'yes' to confirm or 'no' to edit.\n{summary}"
            elif self.current_step == "vendor_confirm":
                if user_input.lower() == "yes":
                    self.current_step = "complete"
                    insert_visitor_to_db(
                        visitor_type="vendor",
                        full_name=self.visitor_info.visitor_name or "",
                        cnic=self.visitor_info.visitor_cnic or "",
                        phone=self.visitor_info.visitor_phone or "",
                        host="Admin",
                        purpose=f"Vendor visit - {self.visitor_info.supplier}",
                        is_group_visit=self.visitor_info.is_group_visit,
                        group_members=self.visitor_info.group_members,
                        total_members=self.visitor_info.total_members
                    )
                    try:
                        if self.ai.graph_client is not None:
                            access_token = self.ai.get_system_account_token()
                            system_user_id = self.ai.get_user_id("saadsaad@dpl660.onmicrosoft.com", access_token)
                            admin_user_id = self.ai.get_user_id("admin_IT@dpl660.onmicrosoft.com", access_token)
                            chat_id = self.ai.create_or_get_chat(admin_user_id, system_user_id, access_token)
                            message = f"A vendor has arrived at reception:\nName: {self.visitor_info.visitor_name}\nSupplier: {self.visitor_info.supplier}\nCNIC: {self.visitor_info.visitor_cnic}\nPhone: {self.visitor_info.visitor_phone}"
                            if self.visitor_info.is_group_visit:
                                message += f"\nGroup size: {self.visitor_info.total_members}"
                                for idx, member in enumerate(self.visitor_info.group_members, 2):
                                    message += f"\nMember {idx}: {member.get('name','')} / {member.get('cnic','')} / {member.get('phone','')}"
                            self.ai.send_message_to_host(chat_id, access_token, message)
                    except Exception as e:
                        print(f"Error in Teams notification process: {e}")
                    return "Your registration is complete."
                elif user_input.lower() == "no":
                    self.current_step = "supplier"
                    supplier_list = "\n".join(f"{idx}. {supplier}" for idx, supplier in enumerate(SUPPLIERS, 1))
                    return f"Please select your supplier company:\n{supplier_list}"
                else:
                    return "Please type 'yes' to confirm or 'no' to edit."
            elif self.current_step == "complete":
                return "Your registration is complete."

        # Generate AI response for the current step
        context = {
            "current_step": self.current_step,
            **self.visitor_info.to_dict()
        }
        return await self.get_ai_response(user_input, context)
    
    async def get_ai_response(self, user_input: str, context: dict) -> str:
        """Get a response from the AI model based on the current context"""
        # Use synchronous version for simplicity
        return self.ai.process_visitor_input(user_input, context)

    async def run(self):
        # Display hardcoded welcome message
        from prompts import HARDCODED_WELCOME
        print(f"\nDPL: {HARDCODED_WELCOME}")
        
        while True:
            if self.current_step == "complete":
                print("DPL: Please wait...")
                await asyncio.sleep(2)  # Give user time to read the completion message
                self.reset()
                print(f"\nDPL: {HARDCODED_WELCOME}")
                continue

            user_input = input("You: ").strip()
            if user_input.lower() in ["quit", "exit"]:
                goodbye_context = {"current_step": "complete", "is_exit": True}
                goodbye_response = self.ai.process_visitor_input("quit", goodbye_context)
                print(f"\nDPL: {goodbye_response}")
                break
            
            response = await self.process_input(user_input)
            print(f"\nDPL: {response}")
            
            # After printing response, if we're in complete state,
            # don't wait for user input before resetting

class MessageRequest(BaseModel):
    message: str
    current_step: str
    visitor_info: dict

@app.post("/process-message/")
async def process_message(request: MessageRequest):
    try:
        receptionist = DPLReceptionist()
        
        # Restore state from frontend
        if request.current_step:
            receptionist.current_step = request.current_step
            
        if request.visitor_info:
            # Restore all visitor info attributes
            for k, v in request.visitor_info.items():
                if hasattr(receptionist.visitor_info, k):
                    setattr(receptionist.visitor_info, k, v)
            
            # Restore employee selection mode and matches if needed
            if request.visitor_info.get('employee_selection_mode'):
                receptionist.employee_selection_mode = True
                receptionist.employee_matches = request.visitor_info.get('employee_matches', [])
        
        # Process the message
        response = await receptionist.process_input(request.message)
        
        # Get visitor info as a dict
        visitor_info = {}
        if hasattr(receptionist.visitor_info, 'to_dict'):
            visitor_info = receptionist.visitor_info.to_dict()
        else:
            visitor_info = {k: v for k, v in vars(receptionist.visitor_info).items() 
                          if not k.startswith('_')}
        
        # Add additional state info
        visitor_info['employee_selection_mode'] = receptionist.employee_selection_mode
        visitor_info['employee_matches'] = receptionist.employee_matches
        
        # For complete state, provide special handling
        if receptionist.current_step == 'complete':
            visitor_info['registration_completed'] = True
            response = "Your registration is complete. Thank you for visiting DPL!"
            
        return {
            "response": response,
            "next_step": receptionist.current_step,
            "visitor_info": visitor_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    receptionist = DPLReceptionist()
    asyncio.run(receptionist.run())
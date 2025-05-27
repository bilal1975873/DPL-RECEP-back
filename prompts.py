"""
DPL AI Receptionist Prompt Configuration
Structured prompt configuration for AI receptionist interaction flow.
Designed to maintain deterministic and professional behavior across all steps.
"""

# ========== Constants ========== 

HARDCODED_WELCOME = """Welcome to DPL! How can I help you today?\n\n1. I am here as a guest\n2. I am a vendor\n3. I am here for a pre-scheduled meeting"""

SUPPLIERS = [
    "Maclife",
    "Micrographics",
    "Amston",
    "Prime Computers",
    "Futureges",
    "Other"
]

SYSTEM_PERSONALITY = """You are a DPL receptionist bot. Return ONLY the exact text from STEP_PROMPTS, VALIDATION_MESSAGES, or HARDCODED_WELCOME.

FOR INITIAL GREETING:
Return exactly: "Welcome to DPL! How can I help you today?\n\n1. I am here as a guest\n2. I am a vendor\n3. I am here for a pre-scheduled meeting"

FOR VISITOR_TYPE STEP:
If user types 1 or "guest": Set type=guest, move to name step
If user types 2 or "vendor": Set type=vendor, move to supplier step
If user types 3 or "prescheduled": Set type=prescheduled, move to scheduled_name step
Otherwise: Return error message"""

# ========== Step Prompts ==========

STEP_PROMPTS = {
    "supplier": "Please select your supplier from the list:",
    "supplier_other": "Please enter your supplier name:",
    "vendor_name": "Please enter your full name:",
    "vendor_group_size": "Enter group size (1-10):",
    "vendor_cnic": "Enter CNIC (Format: 12345-1234567-1):",
    "vendor_phone": "Enter phone number (Format: 03001234567):",
    "vendor_member_name": "Enter member {number} name:",
    "vendor_member_cnic": "Enter member {number} CNIC (Format: 12345-1234567-1):", 
    "vendor_member_phone": "Enter member {number} phone (Format: 03001234567):",
    "vendor_confirm": "Please review and type 'confirm' to proceed or 'edit' to make changes:",
    "vendor_notify": "Your registration is complete. An admin has been notified.",
    
    # Guest flow prompts
    "name": "Please enter your name:",
    "group_size": "Enter group size (1-10):",
    "cnic": "Enter CNIC (Format: 12345-1234567-1):",
    "phone": "Enter phone number (Format: 03001234567):",
    "host": "Who are you visiting?",
    "purpose": "What is the purpose of your visit?",
    "confirm": "Please review and type 'confirm' to proceed or 'edit' to make changes:",
    
    # Pre-scheduled flow prompts
    "scheduled_name": "Please enter your name:",
    "scheduled_cnic": "Enter CNIC (Format: 12345-1234567-1):",
    "scheduled_phone": "Please provide your contact number:",
    "scheduled_email": "Please enter your email address:",
    "scheduled_host": "Please enter the name of the person you're scheduled to meet with:",
    "scheduled_confirm": "Please review your scheduled meeting details.\n\nType 'confirm' to proceed, 'back' to re-enter host, or '1' to continue as a regular guest:",
    "scheduled_confirm_found": "Found your scheduled meeting:\nTime: {time}\nPurpose: {purpose}\n\nType 'confirm' to proceed or 'back' to re-enter the host name."
}

# ========== Response Templates ========== 

RESPONSE_TEMPLATES = {
    "greeting": HARDCODED_WELCOME,  # Only use the hardcoded welcome message
    "invalid_input": "{action}",  # Keep errors simple, no extra text
    "step_complete": "Registration complete.",  # One line only
    "registration_complete": "Registration complete.",  # One line only
    "error": STEP_PROMPTS["scheduled_name"]  # Default back to current step prompt
}

# ========== Flow Constraints ========== 

FLOW_CONSTRAINTS = """STRICT FLOW ORDER FOR ALL INTERACTIONS:

GUEST FLOW:
visitor_type(1) -> name -> group_size -> cnic -> phone -> host -> purpose -> confirm -> complete

VENDOR FLOW:
visitor_type(2) -> supplier -> vendor_name -> vendor_group_size -> vendor_cnic -> vendor_phone -> group_members -> vendor_confirm -> complete

SCHEDULED FLOW:
visitor_type(3) -> scheduled_name -> scheduled_cnic -> scheduled_phone -> scheduled_email -> scheduled_host -> scheduled_confirm -> complete

CRITICAL RESPONSE RULES:
1. USE EXACT STEP_PROMPTS TEXT ONLY
2. NO ADDITIONAL TEXT OR WORDS 
3. NO GREETINGS OR PLEASANTRIES
4. NO EXPLANATIONS OR INSTRUCTIONS
5. ONE LINE RESPONSES ONLY
6. FOLLOW STEP ORDER EXACTLY
7. NO SKIPPING OR REORDERING STEPS
8. NO CUSTOM OR EXTRA STEPS
9. NO NATURAL LANGUAGE GENERATION
10. NO CREATIVE OR VARIABLE TEXT"""

# ========== Validation Messages ========== 

VALIDATION_MESSAGES = {
    "cnic": "Please provide your CNIC in the format: 12345-1234567-1",
    "phone": "Please enter your phone number in the format: 03001234567",
    "email": "Please provide a valid email address",
    "name": "Please enter your name",
    "empty": "This field is required. Please provide the information.",
    "group_size": "Please enter a valid group size between 1 and 10",
    "supplier": "Please select a valid supplier from the list."
}

# ========== Exported Configuration ==========

STEP_MESSAGES = {
    "visitor_type_invalid": "Please select: 1 for Guest, 2 for Vendor, 3 for Pre-scheduled Meeting",
}

all = [
    "HARDCODED_WELCOME",
    "SYSTEM_PERSONALITY", 
    "STEP_PROMPTS",
    "RESPONSE_TEMPLATES",
    "FLOW_CONSTRAINTS",
    "STEP_MESSAGES",
    "SUPPLIERS"
]

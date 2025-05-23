# Guest flow requirements, steps, and validation logic
import re
from typing import Dict, Any, Optional
from datetime import datetime

# Validation patterns with strict rules
NAME_PATTERN = r"^[A-Za-z\s]{2,50}$"  # Only letters and spaces, 2-50 chars
CNIC_PATTERN = r"^\d{5}-\d{7}-\d{1}$"  # Format: 12345-1234567-1
PHONE_PATTERN = r"^03\d{9}$"  # Format: 03001234567
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

# Hardcoded validation error messages
ERROR_MESSAGES = {
    "name": "Name should only contain letters and spaces (2-50 characters)",
    "cnic": "CNIC must be in format: 12345-1234567-1",
    "phone": "Phone number must be in format: 03001234567",
    "email": "Please enter a valid email address",
    "group_size": "Group size must be a number between 1 and 10",
    "empty": "This field cannot be empty",
    "supplier": "Please select a valid supplier from the list.",
    "vendor_name": "Please enter a valid name for the vendor."
}

def validate_name(name: str) -> bool:
    """Validate name: only letters and spaces allowed"""
    if not name or len(name.strip()) < 2:
        return False
    return bool(re.match(NAME_PATTERN, name))

def validate_cnic(cnic: str) -> bool:
    """Validate CNIC format"""
    return bool(re.match(CNIC_PATTERN, cnic))

def validate_phone(phone: str) -> bool:
    """Validate phone number format"""
    return bool(re.match(PHONE_PATTERN, phone))

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(re.match(EMAIL_PATTERN, email))

def validate_group_size(size: str) -> bool:
    """Validate group size (1-10)"""
    try:
        size_int = int(size)
        return 1 <= size_int <= 10
    except ValueError:
        return False

def get_error_message(field: str) -> str:
    """Get hardcoded error message for field"""
    return ERROR_MESSAGES.get(field, "Error: Invalid input")

SUPPLIERS = [
    "Maclife",
    "Micrographics",
    "Amston",
    "Prime Computers",
    "Futureges",
    "Other"
]

# Scheduled flow requirements and steps
scheduled_flow = {
    "required_fields": ["visitor_name", "visitor_phone", "visitor_email", "host_confirmed"],
    "steps": ["scheduled_name", "scheduled_phone", "scheduled_email", "scheduled_host", "scheduled_confirm", "complete"],
    "validations": {
        "visitor_phone": validate_phone,
        "visitor_email": validate_email
    }
}

# Guest flow requirements and steps
guest_flow = {
    "required_fields": ["visitor_name", "visitor_cnic", "visitor_phone", "host_confirmed", "purpose"],
    "steps": ["name", "group_size", "cnic", "phone", "host", "purpose", "confirm", "complete"],
    "validations": {
        "visitor_cnic": validate_cnic,
        "visitor_phone": validate_phone
    }
}

# Vendor flow requirements and steps
vendor_flow = {
    "required_fields": ["supplier", "visitor_name", "visitor_cnic", "visitor_phone"],
    "steps": ["supplier", "vendor_name", "vendor_group_size", "vendor_cnic", "vendor_phone", "vendor_confirm", "complete"],
    "validations": {
        "supplier": lambda x: x in SUPPLIERS or x == "Other",
        "visitor_cnic": validate_cnic,
        "visitor_phone": validate_phone,
        "vendor_name": validate_name,
        "group_size": validate_group_size
    }
}
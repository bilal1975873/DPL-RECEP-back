# Guest flow requirements, steps, and validation logic
import re
from typing import Dict, Any, Optional
from datetime import datetime

# Validation patterns
CNIC_PATTERN = r"^\d{5}-\d{7}-\d{1}$"  # Format: 12345-1234567-1
PHONE_PATTERN = r"^\+?\d{11,13}$"  # Format: +923001234567 or 03001234567

def validate_cnic(cnic: str) -> bool:
    return bool(re.match(CNIC_PATTERN, cnic))

def validate_phone(phone: str) -> bool:
    return bool(re.match(PHONE_PATTERN, phone))

# Guest flow requirements and steps
# Sync with main.py: name, group_size, cnic, phone, host, purpose, confirm, complete
guest_flow = {
    "required_fields": ["visitor_name", "visitor_cnic", "visitor_phone", "host_confirmed", "purpose"],
    "steps": ["name", "group_size", "cnic", "phone", "host", "purpose", "confirm", "complete"],
    "validations": {
        "visitor_cnic": validate_cnic,
        "visitor_phone": validate_phone
    }
}

# Vendor flow requirements and steps
SUPPLIERS = [
    "Maclife",
    "Micrographics",
    "Amston",
    "Prime Computers",
    "Futureges",
    "Other"
]

# Sync with main.py: supplier, supplier_other, vendor_name, vendor_group_size, vendor_cnic, vendor_phone, vendor_confirm, complete
vendor_flow = {
    "required_fields": ["supplier", "visitor_name", "visitor_cnic", "visitor_phone"],
    "steps": ["supplier", "supplier_other", "vendor_name", "vendor_group_size", "vendor_cnic", "vendor_phone", "vendor_confirm", "complete"],
    "validations": {
        "visitor_cnic": validate_cnic,
        "visitor_phone": validate_phone
    }
}
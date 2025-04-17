"""
Utility functions for the RenPay application.
This module provides common utilities that can be used across the application.
"""

import logging
import os
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import json
import time
import uuid
import re
from dotenv import load_dotenv
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("renpay-api.log", mode="a")
    ]
)

logger = logging.getLogger("renpay-utils")

# Load environment variables
load_dotenv()

def get_env_var(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Get environment variable with validation.
    If required and not found, raises ValueError.
    """
    value = os.getenv(key, default)
    if required and not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

def format_currency(amount: float, currency: str = "INR") -> str:
    """Format amount with currency symbol"""
    currency_symbols = {
        "INR": "₹",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥"
    }
    
    symbol = currency_symbols.get(currency, currency)
    
    if currency == "INR":
        # Format with Indian number system (e.g., 1,00,000.00)
        # First, format with commas for thousands
        formatted = f"{symbol} {amount:,.2f}"
        
        # Replace with Indian number format
        parts = formatted.split('.')
        parts[0] = parts[0].replace(",", "x")
        parts[0] = parts[0].replace("x", ",", 1) if "x" in parts[0] else parts[0]
        
        integer_part = parts[0].replace("x", "")
        groups = []
        
        # Keep the symbol and possible first comma
        if "," in parts[0]:
            first_comma_index = parts[0].find(",")
            groups.append(parts[0][:first_comma_index+1])
            integer_part = parts[0][first_comma_index+1:]
        else:
            symbol_part = parts[0].split(" ")[0]
            groups.append(f"{symbol_part} ")
            integer_part = parts[0][len(symbol_part)+1:]
        
        # Process remaining digits in groups of 2 (except the first group which is 3)
        if len(integer_part) <= 3:
            groups.append(integer_part)
        else:
            groups.append(integer_part[:-3])
            remaining = integer_part[-3:]
            
            while remaining:
                if len(remaining) <= 2:
                    groups.append(remaining)
                    break
                else:
                    groups.append(remaining[:2])
                    remaining = remaining[2:]
        
        parts[0] = ",".join(groups)
        return ".".join(parts)
    else:
        # Standard international format
        return f"{symbol} {amount:,.2f}"

def generate_unique_id(prefix: str = "") -> str:
    """
    Generate a unique ID with optional prefix.
    Format: [prefix]-[timestamp]-[uuid]
    """
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4()).split("-")[0]
    return f"{prefix}-{timestamp}-{unique_id}" if prefix else f"{timestamp}-{unique_id}"

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it's safe to use in a file system.
    Removes special characters and limits length.
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Limit length
    return sanitized[:100]

def load_json_file(file_path: str) -> Dict[str, Any]:
    """
    Load a JSON file with error handling
    """
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"JSON file not found: {file_path}")
            return {}
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in file: {file_path}")
        return {}
    except Exception as e:
        logger.error(f"Error loading JSON file {file_path}: {str(e)}")
        return {}

def save_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """
    Save data to a JSON file with error handling
    Returns success status
    """
    try:
        # Create directory if it doesn't exist
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON file {file_path}: {str(e)}")
        return False

def validate_phone_number(phone: str) -> bool:
    """
    Validate a phone number with basic formatting
    """
    # Remove common formatting characters
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    # Check if it's a valid number (adjust as needed for your country format)
    return cleaned.isdigit() and 8 <= len(cleaned) <= 15

def validate_tax_id(tax_id: str) -> bool:
    """
    Validate a GST/tax ID format for India
    GSTIN format: 2 digit state code + 10 digit PAN + 1 digit entity number + 1 digit check sum
    """
    # Basic format check for India's GST
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}[Z]{1}[A-Z0-9]{1}$"
    return bool(re.match(pattern, tax_id.upper()))

def calculate_due_date(issue_date: datetime, payment_terms_days: int = 30) -> datetime:
    """
    Calculate due date based on issue date and payment terms
    """
    return issue_date + datetime.timedelta(days=payment_terms_days)

def parse_date_string(date_str: str) -> Optional[datetime]:
    """
    Parse a date string in multiple formats
    """
    formats = [
        "%Y-%m-%d",           # 2023-01-31
        "%d/%m/%Y",           # 31/01/2023
        "%m/%d/%Y",           # 01/31/2023
        "%d-%m-%Y",           # 31-01-2023
        "%m-%d-%Y",           # 01-31-2023
        "%d %b %Y",           # 31 Jan 2023
        "%d %B %Y",           # 31 January 2023
    ]
    
    for date_format in formats:
        try:
            return datetime.strptime(date_str, date_format)
        except ValueError:
            continue
    
    return None

# Export common utilities
__all__ = [
    'get_env_var',
    'format_currency',
    'generate_unique_id',
    'sanitize_filename',
    'load_json_file',
    'save_json_file',
    'validate_phone_number',
    'validate_tax_id',
    'calculate_due_date',
    'parse_date_string'
]
"""MMA Mess — single Flask application."""
import calendar
import math
import os
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hmac import compare_digest
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from bson import ObjectId
import certifi
from click import ClickException
from dotenv import dotenv_values, load_dotenv
from flask import (
    Blueprint,
    Flask,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_pymongo import PyMongo
from pymongo import ASCENDING, DESCENDING, ReplaceOne, ReturnDocument
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    DuplicateKeyError,
    PyMongoError,
    ServerSelectionTimeoutError,
)
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
if (ROOT / ".env").exists() and os.environ.get("FLASK_CONFIG") != "production":
    load_dotenv(ROOT / ".env", override=False)

mongo = PyMongo()


class MongoInitializationError(Exception):
    def __init__(self, category):
        super().__init__(category)
        self.category = category


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    MONGODB_URI = os.environ.get("MONGODB_URI")
    MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE")
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN")


class DevelopmentConfig(Config):
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_urlsafe(32)
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/")
    MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "mma_hostel_mess")
    FRONTEND_ORIGIN = os.environ.get(
        "FRONTEND_ORIGIN",
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:8080,http://127.0.0.1:8080",
    )
    DEBUG = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN")
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True


class TestingConfig:
    DEBUG = True
    TESTING = True
    SECRET_KEY = "test-only-session-secret"
    MONGODB_URI = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=250"
    MONGODB_DATABASE = "mma_hostel_mess_test"
    FRONTEND_ORIGIN = "http://localhost:5000"
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


class User(UserMixin):
    def __init__(self, data=None):
        if data:
            self.id = data.get("id")
            self.name = data.get("name")
            self.room = data.get("room")
            self.phone = data.get("phone")
            self.email = data.get("email")
            self.password_hash = data.get("password_hash")
            role = str(data.get("role") or "student").strip().lower()
            self.role = "student" if role == "resident" else role
            self.status = data.get("status", "active")
            self.created_at = data.get("created_at")
            self.updated_at = data.get("updated_at")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "room": self.room,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_id(self):
        return str(self.id)


# --- entry_rules.py ---
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


MESS_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_TOMORROW_CUTOFF = "23:00"


def mess_now(now=None):
    if now is None:
        return datetime.now(MESS_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=MESS_TIMEZONE)
    return now.astimezone(MESS_TIMEZONE)


def tomorrow_date(now=None):
    return mess_now(now).date() + timedelta(days=1)


def cutoff_datetime(settings, now=None):
    cutoff_value = settings.get("tomorrowCutoff", DEFAULT_TOMORROW_CUTOFF)
    try:
        cutoff_time = time.fromisoformat(cutoff_value)
    except (TypeError, ValueError):
        raise ValueError("The configured tomorrow entry cutoff is invalid.")
    if cutoff_time.second or cutoff_time.microsecond:
        raise ValueError("The configured tomorrow entry cutoff must use HH:MM.")
    local_now = mess_now(now)
    return datetime.combine(local_now.date(), cutoff_time, MESS_TIMEZONE)


def tomorrow_entry_is_closed(settings, now=None):
    local_now = mess_now(now)
    return local_now >= cutoff_datetime(settings, local_now)


def cooking_date(settings, now=None):
    local_now = mess_now(now)
    if local_now >= cutoff_datetime(settings, local_now):
        return local_now.date() + timedelta(days=1)
    return local_now.date()


def parse_entry_date(value):
    if not isinstance(value, str):
        raise ValueError("Entry date must use YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Entry date must use YYYY-MM-DD format.")
    if parsed.isoformat() != value:
        raise ValueError("Entry date must use YYYY-MM-DD format.")
    return parsed

# --- room_sorting.py ---
"""Shared custom room ordering for backend-generated lists and reports."""

import re

ROOM_ORDER = (
    "G1", "G2", "G3",
    "F1", "F2", "F3",
    "S1", "S2", "S3",
    "T1", "T2", "T3",
)
ROOM_PRIORITIES = {room: index for index, room in enumerate(ROOM_ORDER)}


def normalize_room(room):
    return re.sub(r"[\s/_-]+", "", str(room or "").strip().upper())


def get_room_priority(room):
    return ROOM_PRIORITIES.get(normalize_room(room), len(ROOM_ORDER))


def room_record_sort_key(record):
    room = record.get("room") if isinstance(record, dict) else ""
    normalized_room = normalize_room(room)
    priority = get_room_priority(room)
    name = ""
    if isinstance(record, dict):
        name = (
            record.get("name")
            or record.get("user_name")
            or record.get("userName")
            or record.get("user_id")
            or record.get("user")
            or record.get("id")
            or ""
        )
    unknown_room = "" if priority < len(ROOM_ORDER) else normalized_room
    return priority, unknown_room, str(name).casefold(), str(name)

# --- meal_points.py ---
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def quantity(value):
    if isinstance(value, bool):
        return 0
    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return 0
    if not number.is_finite():
        return 0
    return max(0, int(number))


def calculate_meal_points(
    expected,
    actual,
    approved_quantity,
    point_value,
    *,
    after_cutoff,
    permission_fee=0,
    cancelled=False,
    permission_pending=False,
):
    """Return billable meal quantities and point components from authoritative inputs."""
    expected = quantity(expected)
    entered_quantity = quantity(actual)
    actual = expected if actual is None and not after_cutoff else quantity(actual)
    approved_quantity = min(
        max(0, actual - expected),
        quantity(approved_quantity),
    )

    try:
        point = Decimal(str(point_value or 0))
        fee = Decimal(str(permission_fee or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Meal points and permission fees must be numeric.")
    if not point.is_finite() or point < 0 or not fee.is_finite() or fee < 0:
        raise ValueError("Meal points and permission fees must be finite and non-negative.")

    if cancelled:
        return {
            "expected_quantity": 0,
            "actual_quantity": 0,
            "scheduled_quantity": expected,
            "entered_quantity": entered_quantity,
            "billable_quantity": 0,
            "approved_quantity": 0,
            "normal_meal_points": Decimal("0.00"),
            "unauthorized_quantity": 0,
            "unauthorized_meal_points": Decimal("0.00"),
            "permission_fee": Decimal("0.00"),
            "unauthorized_fine_points": Decimal("0.00"),
            "missing_fine_points": Decimal("0.00"),
            "additional_fine": Decimal("0.00"),
            "final_billable_points": Decimal("0.00"),
            "fine_reason": "",
            "cancelled": True,
        }

    expected_quantity = min(actual, expected)
    missing_quantity = max(0, expected - actual) if after_cutoff else 0
    unauthorized_quantity = (
        0
        if permission_pending
        else max(0, actual - expected - approved_quantity)
    )
    normal_quantity = expected_quantity + missing_quantity + approved_quantity
    billable_quantity = (
        normal_quantity + missing_quantity + 2 * unauthorized_quantity
    )
    normal_points = Decimal(normal_quantity) * point
    unauthorized_points = Decimal(unauthorized_quantity) * point
    additional_fine = (
        Decimal(missing_quantity + unauthorized_quantity) * point
    )
    permission_points = Decimal(approved_quantity) * fee
    final_points = (
        normal_points
        + unauthorized_points
        + additional_fine
        + permission_points
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    reasons = []
    if unauthorized_quantity:
        reasons.append("Unauthorized extra portions charged at double points")
    if missing_quantity:
        reasons.append("Missing expected portions charged at double points")

    return {
        "expected_quantity": expected,
        "actual_quantity": actual,
        "scheduled_quantity": expected,
        "entered_quantity": entered_quantity,
        "billable_quantity": billable_quantity,
        "approved_quantity": approved_quantity,
        "normal_meal_points": normal_points.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        "unauthorized_quantity": unauthorized_quantity,
        "unauthorized_meal_points": unauthorized_points.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        "permission_fee": permission_points.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        "unauthorized_fine_points": (
            Decimal(unauthorized_quantity) * point
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "missing_fine_points": (
            Decimal(missing_quantity) * point
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "additional_fine": additional_fine.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        "final_billable_points": final_points,
        "fine_reason": "; ".join(reasons),
    }

# --- models_mongo.py ---
"""
MongoDB models and database helper functions
for MMA Hostel Mess Management.
"""

import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash



# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def get_collection(name):
    """Return a MongoDB collection."""
    if mongo.db is None:
        raise RuntimeError("MongoDB database is not initialized.")

    return mongo.db[name]


def ensure_indexes(app):
    """Apply additive indexes; run explicitly using ``flask ensure-indexes``."""
    indexes = (
        (
            "bills",
            [("user_id", 1), ("billing_month", 1)],
            "bill_user_month_unique",
            {"unique": True},
        ),
        (
            "bill_drafts",
            [("user_id", 1), ("billing_month", 1)],
            "bill_draft_user_month_unique",
            {"unique": True},
        ),
        ("general_settings", [("key", 1)], "general_settings_key_unique", {"unique": True}),
        (
            "mess_entries",
            [("user_id", 1), ("date", 1)],
            "user_date_v2_unique",
            {"unique": True, "partialFilterExpression": {"writeVersion": 2}},
        ),
        (
            "meal_records",
            [("user_id", 1), ("date", 1)],
            "user_date_v2_unique",
            {"unique": True, "partialFilterExpression": {"writeVersion": 2}},
        ),
        ("mess_entries", [("date", 1), ("updated_at", -1)], "entry_date_updated", {}),
        ("meal_records", [("date", 1), ("updated_at", -1)], "meal_record_date_updated", {}),
        (
            "meal_cancellations",
            [("date", 1), ("meal_type", 1)],
            "meal_cancellation_date_meal_unique",
            {"unique": True},
        ),
        (
            "notifications",
            [("dedupeKey", 1)],
            "notification_dedupe_unique",
            {"unique": True, "partialFilterExpression": {"dedupeKey": {"$type": "string"}}},
        ),
        (
            "meal_cancellation_adjustments",
            [("dedupeKey", 1)],
            "cancellation_adjustment_dedupe_unique",
            {"unique": True, "partialFilterExpression": {"dedupeKey": {"$type": "string"}}},
        ),
        (
            "no_food_requests",
            [("user_id", 1), ("date", 1), ("meal", 1)],
            "no_food_user_date_meal_unique",
            {"unique": True},
        ),
        (
            "no_food_requests",
            [("status", 1), ("date", 1), ("requested_at", -1)],
            "no_food_status_date_requested",
            {},
        ),
    )
    for collection_name, keys, index_name, options in indexes:
        collection = get_collection(collection_name)
        if index_name in {
            "bill_user_month_unique",
            "bill_draft_user_month_unique",
            "general_settings_key_unique",
        }:
            existing_indexes = collection.index_information()
            if any(
                index.get("key") == keys and index.get("unique") is True
                for index in existing_indexes.values()
            ):
                continue
        collection.create_index(keys, name=index_name, **options)
    app.logger.info("Ensured %d MongoDB indexes.", len(indexes))


def normalize_email(email):
    """Normalize an email address."""
    return str(email or "").strip().lower()


def normalize_phone(phone):
    """Normalize a phone number to digits."""
    return re.sub(r"\D", "", str(phone or ""))


# --------------------------------------------------
# USER OPERATIONS
# --------------------------------------------------

def create_user(user_data):
    """
    Create a user with a hashed password.

    The caller must supply a unique user ID and valid
    account details.
    """
    data = dict(user_data)

    password = data.pop("password", None)

    if password is not None:
        data["password_hash"] = generate_password_hash(password)

    if not data.get("password_hash"):
        raise ValueError("A password or password_hash is required.")

    if not data.get("id"):
        raise ValueError("A unique user ID is required.")

    if data.get("email"):
        data["email"] = normalize_email(data["email"])

    if data.get("phone"):
        data["phone"] = normalize_phone(data["phone"])

    data.setdefault("status", "active")
    data.setdefault("role", "student")

    now = utc_now()
    data["created_at"] = now
    data["updated_at"] = now

    return get_collection("users").insert_one(data)


def get_user(user_id):
    """Get a user by application-level ID."""
    if user_id is None:
        return None

    return get_collection("users").find_one({
        "id": str(user_id)
    })


def get_approved_no_food_map(date_value=None, month=None):
    """Return approved no-food requests keyed by user/date/meal.

    This is deliberately a separate read model from ordinary meal entries so
    an approved zero-point meal remains auditable and cannot be mistaken for a
    missing or ordinary zero-quantity entry.
    """
    if date_value and month:
        raise ValueError("Specify either date_value or month, not both.")
    if date_value:
        query = {"status": "approved", "date": date_value}
    elif month:
        query = {
            "status": "approved",
            "date": {"$regex": "^" + re.escape(str(month)) + "-"},
        }
    else:
        query = {"status": "approved"}

    result = {}
    for request in get_collection("no_food_requests").find(query):
        user_id = str(request.get("user_id") or "").strip().upper()
        date_key = str(request.get("date") or "")[:10]
        meal = str(request.get("meal") or "").strip().lower()
        if user_id and date_key and meal in {"b", "l", "d"}:
            result[(user_id, date_key, meal)] = request
    return result


def get_user_by_email(email):
    """Find a user by email address, ignoring case."""
    email = normalize_email(email)

    if not email:
        return None

    return get_collection("users").find_one({
        "email": {
            "$regex": "^" + re.escape(email) + "$",
            "$options": "i",
        }
    })


def get_user_by_identity(identity):
    """
    Find a user by application ID, email, or phone number.
    """
    identity = str(identity or "").strip()

    if not identity:
        return None

    digits = normalize_phone(identity)

    conditions = [
        {"id": identity},
        {
            "email": {
                "$regex": "^" + re.escape(identity) + "$",
                "$options": "i",
            }
        },
    ]

    if digits:
        conditions.append({"phone": digits})

    # Include the original phone value for legacy records.
    if identity != digits:
        conditions.append({"phone": identity})

    return get_collection("users").find_one({
        "$or": conditions
    })


def get_all_users():
    """Return all users."""
    return list(get_collection("users").find())


def update_user(user_id, updates):
    """Update a user, hashing a supplied new password."""
    if not user_id:
        raise ValueError("A user ID is required.")

    data = dict(updates)

    password_changed = "password" in data
    if password_changed:
        password = data.pop("password")

        if not isinstance(password, str) or len(password) < 6:
            raise ValueError(
                "Password must contain at least 6 characters."
            )

        data["password_hash"] = generate_password_hash(password)

    if data.get("email"):
        data["email"] = normalize_email(data["email"])

    if data.get("phone"):
        data["phone"] = normalize_phone(data["phone"])

    # Never permit an ordinary update to replace the MongoDB _id.
    data.pop("_id", None)

    data["updated_at"] = utc_now()

    updates = {"$set": data}
    if password_changed:
        updates["$inc"] = {"auth_version": 1}

    return get_collection("users").update_one(
        {"id": str(user_id)},
        updates,
    )


def delete_user(user_id):
    """Delete a user by application ID."""
    return get_collection("users").delete_one({
        "id": str(user_id)
    })


# --------------------------------------------------
# REGISTRATION IDENTITY CHECKS
# --------------------------------------------------

def registration_identity_exists(
    email,
    phone,
    exclude_user_id=None
):
    """
    Check approved users and pending registration requests
    for an existing email or phone number.
    """
    email = normalize_email(email)
    phone = normalize_phone(phone)

    identity_conditions = []

    if email:
        identity_conditions.append({
            "email": {
                "$regex": "^" + re.escape(email) + "$",
                "$options": "i",
            }
        })

    if phone:
        identity_conditions.append({
            "phone": phone
        })

    if not identity_conditions:
        return False

    user_query = {"$or": identity_conditions}

    if exclude_user_id:
        user_query["id"] = {
            "$ne": str(exclude_user_id)
        }

    existing_user = get_collection("users").find_one(
        user_query,
        {"_id": 1}
    )

    if existing_user:
        return True

    registration_query = {
        "$or": identity_conditions,
        "status": "pending",
    }

    return (
        get_collection("registration_requests").find_one(
            registration_query,
            {"_id": 1}
        ) is not None
    )


# --------------------------------------------------
# MENU OPERATIONS
# --------------------------------------------------

def save_today_menu(menu_data):
    """Save today's menu."""
    data = dict(menu_data)

    now = utc_now()

    local_today = mess_now().date().isoformat()
    data["updated_at"] = now
    data.setdefault("created_at", now)

    date_value = str(
        data.get("date") or local_today
    )[:10]

    data["date"] = date_value

    return get_collection("today_menu").update_one(
        {"date": date_value},
        {"$set": data},
        upsert=True
    )


def get_today_menu():
    """Get today's menu."""

    today = mess_now().date().isoformat()

    return get_collection("today_menu").find_one({
        "date": today
    })


def save_weekly_menu(menu_data):
    """Replace the weekly menu."""
    collection = get_collection("weekly_menu")
    now = utc_now()

    documents = []

    for item in menu_data:
        document = dict(item)
        document["updated_at"] = now
        document.setdefault("created_at", now)
        documents.append(document)

    # Replace the weekly menu in one bulk operation.
    from pymongo import ReplaceOne

    operations = []

    for index, document in enumerate(documents):
        key = document.get("day", document.get("date", index))

        operations.append(
            ReplaceOne(
                {"day": key} if "day" in document
                else {"date": key} if "date" in document
                else {"_migration_index": index},
                document,
                upsert=True,
            )
        )

    if operations:
        collection.bulk_write(operations, ordered=True)

    # Do not delete existing records that do not match the new
    # payload until the existing menu data format is verified.


def get_weekly_menu():
    """Return the weekly menu."""
    return list(get_collection("weekly_menu").find())


def update_admin_presence(viewer_id, user_id):
    """Record an authenticated admin viewer for a short presence window."""
    now = utc_now()
    collection = get_collection("admin_presence")
    collection.delete_many({"expires_at": {"$lte": now}})
    collection.update_one(
        {"_id": viewer_id},
        {
            "$set": {
                "user_id": str(user_id),
                "updated_at": now,
                "expires_at": now + timedelta(seconds=25),
            }
        },
        upsert=True,
    )
    return len(collection.distinct("user_id", {"expires_at": {"$gt": now}}))


def remove_admin_presence(viewer_id, user_id):
    """Remove one viewer presence belonging to the authenticated admin."""
    return get_collection("admin_presence").delete_one({
        "_id": viewer_id,
        "user_id": str(user_id),
    })


def update_food_points(food_points):
    """Merge food-point records into the existing settings document atomically."""
    collection = get_collection("general_settings")
    now = utc_now()
    collection.update_one(
        {"key": "foodPoints"},
        [
            {
                "$set": {
                    "key": {"$literal": "foodPoints"},
                    "value": {
                        "$mergeObjects": [
                            {"$ifNull": ["$value", {}]},
                            {"$literal": food_points},
                        ]
                    },
                    "updated_at": {"$literal": now},
                }
            }
        ],
        upsert=True,
    )
    document = collection.find_one({"key": "foodPoints"})
    return document.get("value", {}) if document else {}


# --------------------------------------------------
# MESS ENTRY OPERATIONS
# --------------------------------------------------

def create_entry(entry_data):
    """Create or replace a user's entry for a date without adding duplicates."""
    data = dict(entry_data)
    now = utc_now()

    data["updated_at"] = now
    created_at = data.pop("created_at", now)

    user_id = data.get("user_id")
    entry_date = data.get("date")
    if not user_id or not entry_date:
        raise ValueError("user_id and date are required.")

    data["writeVersion"] = 2
    updates = {
        "$set": data,
        "$setOnInsert": {"created_at": created_at},
    }
    if "adminApproved" not in entry_data:
        updates["$unset"] = {"adminApproved": ""}

    return get_collection("mess_entries").update_one(
        {"user_id": user_id, "date": entry_date, "writeVersion": 2},
        updates,
        upsert=True,
    )


def get_entries(date=None):
    """Get mess entries, optionally filtered by date."""
    query = {}

    if date:
        query["date"] = {
            "$regex": "^" + re.escape(str(date))
        }

    return list(get_collection("mess_entries").find(query))


def update_entry(entry_id, updates):
    """Update a mess entry by MongoDB ObjectId."""
    data = dict(updates)
    data.pop("_id", None)
    data["writeVersion"] = 2
    data["updated_at"] = utc_now()

    if isinstance(entry_id, str):
        if not ObjectId.is_valid(entry_id):
            raise ValueError("Invalid mess entry ID.")

        entry_id = ObjectId(entry_id)

    return get_collection("mess_entries").update_one(
        {"_id": entry_id},
        {"$set": data}
    )


def delete_entry(entry_id):
    """Delete a mess entry by MongoDB ObjectId."""
    if isinstance(entry_id, str):
        if not ObjectId.is_valid(entry_id):
            raise ValueError("Invalid mess entry ID.")

        entry_id = ObjectId(entry_id)

    return get_collection("mess_entries").delete_one({
        "_id": entry_id
    })


# --------------------------------------------------
# MEAL RECORD OPERATIONS
# --------------------------------------------------

def save_meal_record(record_data):
    """Save or update a meal record."""
    data = dict(record_data)

    if not data.get("user_id") or not data.get("date"):
        raise ValueError("user_id and date are required.")

    now = utc_now()
    data["updated_at"] = now
    data["writeVersion"] = 2
    data.setdefault("created_at", now)

    return get_collection("meal_records").update_one(
        {
            "user_id": data["user_id"],
            "date": data["date"],
        },
        {"$set": data},
        upsert=True
    )


def get_meal_records(date=None):
    """Get meal records."""
    query = {}

    if date:
        query["date"] = {
            "$regex": "^" + re.escape(str(date))
        }

    return list(get_collection("meal_records").find(query))


# --------------------------------------------------
# BILL OPERATIONS
# --------------------------------------------------

def create_bill(bill_data):
    """Create a bill."""
    data = dict(bill_data)
    now = utc_now()

    data["created_at"] = now
    data["updated_at"] = now

    return get_collection("bills").insert_one(data)


def get_bills(user_id=None, month=None):
    """Get bills by user and/or billing month."""
    query = {}

    if user_id:
        query["user_id"] = user_id

    if month:
        query["billing_month"] = month

    return list(get_collection("bills").find(query))


def update_bill(bill_id, updates):
    """Update a bill by MongoDB ObjectId."""
    data = dict(updates)
    data.pop("_id", None)
    data["updated_at"] = utc_now()

    if isinstance(bill_id, str):
        if not ObjectId.is_valid(bill_id):
            raise ValueError("Invalid bill ID.")

        bill_id = ObjectId(bill_id)

    return get_collection("bills").update_one(
        {"_id": bill_id},
        {"$set": data}
    )


# --------------------------------------------------
# NOTIFICATIONS
# --------------------------------------------------

def create_notification(notif_data):
    """Create a notification."""
    data = dict(notif_data)
    data["created_at"] = utc_now()

    return get_collection("notifications").insert_one(data)


def get_notifications():
    """Return the 50 newest notifications."""
    return list(
        get_collection("notifications")
        .find()
        .sort("created_at", -1)
        .limit(50)
    )


# --------------------------------------------------
# FEEDBACK
# --------------------------------------------------

def create_feedback(feedback_data):
    """Create feedback."""
    data = dict(feedback_data)
    data["created_at"] = utc_now()

    return get_collection("feedback").insert_one(data)


def get_feedback(user_id=None):
    """Return the newest feedback records, optionally for one user."""
    query = {"user_id": user_id} if user_id else {}
    return list(
        get_collection("feedback")
        .find(query)
        .sort("created_at", -1)
        .limit(100)
    )


def save_feedback(feedback_data):
    """Create or update a user's feedback for one meal."""
    data = dict(feedback_data)
    if not data.get("user_id") or not data.get("meal"):
        raise ValueError("user_id and meal are required.")
    now = utc_now()
    data["updated_at"] = now
    return get_collection("feedback").update_one(
        {"user_id": data["user_id"], "meal": data["meal"]},
        {
            "$set": data,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

def save_settings(settings_data):
    """Save application settings."""
    collection = get_collection("general_settings")
    now = utc_now()

    for key, value in settings_data.items():
        result = collection.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "value": value,
                    "updated_at": now,
                }
            },
            upsert=True
        )
        if not result.acknowledged:
            raise RuntimeError("The settings write was not acknowledged.")


def get_settings():
    """Return application settings as a dictionary."""
    settings = {}

    for document in get_collection("general_settings").find():
        settings[document["key"]] = document["value"]

    return settings


# --------------------------------------------------
# REGISTRATION REQUESTS
# --------------------------------------------------

def create_registration(reg_data):
    """Create a pending registration request with a hashed password."""
    data = dict(reg_data)

    password = data.pop("password", None)

    if password is not None:
        data["password_hash"] = generate_password_hash(password)

    if not data.get("password_hash"):
        raise ValueError("A password is required.")

    data["email"] = normalize_email(data.get("email"))
    data["phone"] = normalize_phone(data.get("phone"))

    data["status"] = "pending"

    now = utc_now()
    data["created_at"] = now
    data["updated_at"] = now

    return get_collection("registration_requests").insert_one(data)


def get_pending_registrations():
    """Return pending registration requests."""
    return list(
        get_collection("registration_requests").find({
            "status": "pending"
        })
    )


def update_registration(reg_id, updates):
    """Update a registration request by MongoDB ObjectId."""
    data = dict(updates)
    data.pop("_id", None)
    data["updated_at"] = utc_now()

    if isinstance(reg_id, str):
        if not ObjectId.is_valid(reg_id):
            raise ValueError("Invalid registration ID.")

        reg_id = ObjectId(reg_id)

    return get_collection("registration_requests").update_one(
        {"_id": reg_id},
        {"$set": data}
    )

# --- meal_cancellations.py ---
import re

MEAL_FIELDS = {"b": "breakfast", "l": "lunch", "d": "dinner"}


def get_cancellation(date_value, short):

    if short not in MEAL_FIELDS:
        return None
    return get_collection("meal_cancellations").find_one({
        "date": date_value,
        "meal_type": short,
        "status": "cancelled",
    })


def is_meal_cancelled(date_value, short):
    return get_cancellation(date_value, short) is not None


def list_cancellations(*, date_value=None, month=None):

    query = {"status": "cancelled"}
    if date_value:
        query["date"] = date_value
    elif month:
        query["date"] = {"$regex": "^" + re.escape(month) + "-"}
    cancellations = get_collection("meal_cancellations").find(query)
    result = []
    for cancellation in cancellations:
        item = dict(cancellation)
        if "_id" in item:
            item["_id"] = str(item["_id"])
        result.append(item)
    return result

# --- billing_calculator.py ---
import calendar
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


MESS_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_MEAL_TIMES = {
    "breakfastClose": "11:00",
    "lunchClose": "15:00",
    "dinnerClose": "23:30",
}
MEAL_FIELDS = {"b": "breakfast", "l": "lunch", "d": "dinner"}
WEEKDAY_ORDER = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("Money values must be numeric.")
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Money values must be finite.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _quantity(value):
    try:
        amount = Decimal(str(value or 0))
        return max(Decimal("0"), amount) if amount.is_finite() else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _paise(value):
    return int((money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _from_paise(value):
    return (Decimal(value) / 100).quantize(Decimal("0.01"))


def _split(total, count):
    if count <= 0:
        return []
    base, remainder = divmod(total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _clean_food(name):
    return re.sub(r"\s+", " ", str(name or "").strip()).lower()


def _valid_menu_time(settings, key):
    value = str(settings.get(key) or DEFAULT_MEAL_TIMES[key])
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        value = DEFAULT_MEAL_TIMES[key]
    return time.fromisoformat(value)


def _calculate_bill_data(month, settings, all_users, entries, records, weekly_menu, today_menu, now=None, cancellations=None):
    """Mirror the existing admin point-bill rules using backend database inputs."""
    local_now = now or datetime.now(MESS_TIMEZONE)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=MESS_TIMEZONE)
    else:
        local_now = local_now.astimezone(MESS_TIMEZONE)
    today = local_now.date()

    users = sorted(
        [
            user for user in all_users
            if str(user.get("role", user.get("type", "student"))).lower() != "admin"
            and str(user.get("status", "active")).lower() == "active"
            and user.get("id")
        ],
        key=room_record_sort_key,
    )
    user_ids = {str(user["id"]).upper() for user in users}
    bill_config = settings.get("billConfig") or {}
    if not isinstance(bill_config, dict):
        bill_config = {}
    point_map = settings.get("foodPoints") or {}
    snapshots = settings.get("menuSnapshots") or {}
    adjustments = settings.get("userBillAdjustments") or {}
    discounts = bill_config.get("discounts") or {}
    charges = bill_config.get("charges") or {}
    custom_defs = bill_config.get("customCharges") or []
    expenses = bill_config.get("expenses") or []
    if not isinstance(point_map, dict):
        point_map = {}
    if not isinstance(snapshots, dict):
        snapshots = {}
    if not isinstance(adjustments, dict):
        adjustments = {}
    cancelled_meals = {
        (str(item.get("date") or ""), str(item.get("meal_type") or ""))
        for item in (cancellations or [])
        if isinstance(item, dict) and item.get("status", "cancelled") == "cancelled"
    }

    week_by_day = {str(row.get("day")): row for row in weekly_menu if isinstance(row, dict)}
    records_by_user_date = {}
    ordered_records = sorted(
        records,
        key=lambda record: (
            str(record.get("updated_at") or record.get("created_at") or ""),
            str(record.get("_id") or ""),
        ),
        reverse=True,
    )
    for record in ordered_records:
        record_user = str(record.get("user") or record.get("user_id") or "").upper()
        records_by_user_date.setdefault(
            (record_user, str(record.get("date") or "")[:10]),
            record,
        )
    entries_by_user_date = {}
    ordered_entries = sorted(
        entries,
        key=lambda entry: (
            str(entry.get("updated_at") or entry.get("created_at") or ""),
            str(entry.get("_id") or ""),
        ),
        reverse=True,
    )
    for entry in ordered_entries:
        entry_user = str(entry.get("user") or entry.get("user_id") or "").upper()
        entry_date = str(entry.get("date") or "")
        if entry_user in user_ids and entry_date.startswith(month + "-"):
            entries_by_user_date.setdefault((entry_user, entry_date[:10]), entry)

    def menu_for(day):
        day_key = day.isoformat()
        saved = snapshots.get(day_key)
        if day < today and isinstance(saved, dict):
            return {key: saved.get(key) or "" for key in ("b", "l", "d")}
        row = week_by_day.get(WEEKDAY_ORDER[day.weekday()], {})
        return {key: row.get(key) or "" for key in ("b", "l", "d")}

    meal_closes = {
        "b": _valid_menu_time(settings, "breakfastClose"),
        "l": _valid_menu_time(settings, "lunchClose"),
        "d": _valid_menu_time(settings, "dinnerClose"),
    }
    points = {}
    missing = {}
    days = {}
    for user in users:
        uid = str(user["id"]).upper()
        points[uid] = Decimal("0")
        missing[uid] = []
        days[uid] = set()
    billable_entries = dict(entries_by_user_date)
    for key, record in records_by_user_date.items():
        if key[0] in user_ids and key[1].startswith(month + "-"):
            billable_entries.setdefault(key, {})

    for (uid, day_key), entry in billable_entries.items():
        try:
            day = date.fromisoformat(day_key)
        except ValueError:
            continue
        meals = menu_for(day)
        record = records_by_user_date.get((uid, day_key), {})
        saved_meals = record.get("meals") or {}
        if not isinstance(saved_meals, dict):
            saved_meals = {}
        meal_values = Decimal("0")
        for short, field in MEAL_FIELDS.items():
            if (day_key, short) in cancelled_meals:
                continue
            planned = _quantity(entry.get(field, entry.get(short, 0)))
            saved_meal = saved_meals.get(short)
            no_food = (
                entry.get("noFoodMeals", {}).get(short)
                if isinstance(entry.get("noFoodMeals"), dict)
                else None
            )
            if isinstance(no_food, dict) and no_food.get("review_state"):
                no_food = None
            if not isinstance(no_food, dict) and isinstance(saved_meal, dict):
                no_food = saved_meal.get("noFood")
            if isinstance(no_food, dict) and no_food.get("review_state"):
                no_food = None
            if isinstance(no_food, dict) and no_food.get("status") == "approved":
                # Approved no-food is an auditable exception, never a missing
                # entry or a normal zero quantity that cutoff hydration can
                # turn back into a billable meal.
                meal_values += Decimal("0")
                days[uid].add(day_key)
                continue
            meal_closed = day < today or (
                day == today and local_now.time() >= meal_closes[short]
            )
            if entry.get("adminApproved") or (
                isinstance(saved_meal, dict) and saved_meal.get("optOut")
            ):
                quantity = planned
            else:
                permission = (
                    saved_meal.get("permission")
                    if isinstance(saved_meal, dict)
                    and isinstance(saved_meal.get("permission"), dict)
                    else {}
                )
                approved_quantity = (
                    permission.get("approved_quantity", 0)
                    if permission.get("status") == "approved"
                    else 0
                )
                breakdown = calculate_meal_points(
                    planned,
                    saved_meal.get("q") if isinstance(saved_meal, dict) else None,
                    approved_quantity,
                    1,
                    after_cutoff=meal_closed,
                )
                quantity = breakdown["final_billable_points"]
            food_name = meals[short]
            food = point_map.get(_clean_food(food_name)) if food_name else None
            try:
                point = Decimal(str(food.get("point"))) if isinstance(food, dict) and food.get("point") not in (None, "") else None
                if point is not None and (not point.is_finite() or point < 0):
                    point = None
            except (InvalidOperation, TypeError, ValueError):
                point = None
            if point is None:
                if food_name and food_name not in missing[uid]:
                    missing[uid].append(food_name)
                continue
            meal_values += quantity * point
        points[uid] += meal_values
        days[uid].add(day_key)

    cancel_fines = {uid: Decimal("0") for uid in user_ids}
    for record in records_by_user_date.values():
        if str(record.get("date") or "")[:7] != month:
            continue
        uid = str(record.get("user") or record.get("user_id") or "").upper()
        meals = record.get("meals") or {}
        for short in ("b", "l", "d"):
            if (str(record.get("date") or "")[:10], short) in cancelled_meals:
                continue
            meal = meals.get(short)
            if isinstance(meal, dict) and meal.get("optOut") and _quantity(meal.get("finePoints")) > 0:
                fine_points = money(meal.get("finePoints"))
                if uid in cancel_fines:
                    cancel_fines[uid] += fine_points
    for uid in points:
        points[uid] = money(points[uid] + cancel_fines[uid])
    total_points = money(sum(points.values(), Decimal("0")))

    total_expenses = money(sum(
        (money(item.get("amount", 0)) for item in expenses if isinstance(item, dict)),
        Decimal("0"),
    ))
    per_point = money(total_expenses / total_points) if total_points > 0 else Decimal("0.00")

    def charge_config(key, default_name):
        row = charges.get(key) or {}
        try:
            amount = max(Decimal("0.00"), money(row.get("amount", 0)))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("0.00")
        return {
            "name": str(row.get("name") or default_name),
            "amount": amount,
            "mode": "each" if row.get("mode") == "each" else "split",
        }

    charge_defs = [
        ("fixed", charge_config("fixed", "Fixed Cost")),
        ("water", charge_config("water", "Water Charges")),
        ("reserve", charge_config("reserve", "Reserved Fund")),
    ]
    clean_custom = []
    for index, charge in enumerate(custom_defs if isinstance(custom_defs, list) else []):
        if not isinstance(charge, dict) or not charge.get("name"):
            continue
        charge_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(charge.get("id") or "cc_" + str(index)))
        try:
            amount = max(Decimal("0.00"), money(charge.get("amount", 0)))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("0.00")
        clean_custom.append({
            "id": charge_id,
            "name": str(charge["name"])[:60],
            "mode": "each" if charge.get("mode") == "each" else "split",
            "amount": amount,
        })
    charge_defs.extend((item["id"], item) for item in clean_custom)

    shares = {}
    fixed_discounts = {}
    count = len(users)
    for charge_id, charge in charge_defs:
        base_shares = (
            [_paise(charge["amount"])] * count
            if charge["mode"] == "each"
            else _split(_paise(charge["amount"]), count)
        )
        discounts_for_charge = [0] * count
        if charge_id == "fixed":
            for index, user in enumerate(users):
                uid = str(user["id"]).upper()
                discount = discounts.get(month + "|" + uid) or {}
                if not isinstance(discount, dict):
                    continue
                if discount.get("joiningDate"):
                    try:
                        joining_date = date.fromisoformat(str(discount["joiningDate"]))
                    except ValueError:
                        joining_date = None
                    if joining_date and str(discount["joiningDate"])[:7] == month:
                        month_days = calendar.monthrange(joining_date.year, joining_date.month)[1]
                        remaining = max(0, month_days - joining_date.day)
                        prorated = int((Decimal(base_shares[index] * remaining) / month_days).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                        discounts_for_charge[index] = base_shares[index] - prorated
                    else:
                        discounts_for_charge[index] = _paise(discount.get("amount", 0))
                else:
                    discounts_for_charge[index] = _paise(discount.get("amount", 0))
                discounts_for_charge[index] = max(0, min(base_shares[index], discounts_for_charge[index]))
        received = [0] * count
        total_discount = sum(discounts_for_charge)
        if count > 1 and total_discount:
            recipients = [i for i, value in enumerate(discounts_for_charge) if value == 0]
            if recipients:
                for target, amount in zip(recipients, _split(total_discount, len(recipients))):
                    received[target] += amount
            else:
                for donor, amount in enumerate(discounts_for_charge):
                    others = [i for i in range(count) if i != donor]
                    for target, share in zip(others, _split(amount, len(others))):
                        received[target] += share
        shares[charge_id] = {}
        for index, user in enumerate(users):
            uid = str(user["id"]).upper()
            own_discount = discounts_for_charge[index] if charge_id == "fixed" and count > 1 else 0
            shares[charge_id][uid] = _from_paise(base_shares[index] - own_discount + received[index])
            if charge_id == "fixed":
                fixed_discounts[uid] = _from_paise(own_discount)

    expected = {}
    for user in users:
        uid = str(user["id"]).upper()
        point_amount = money(points[uid] * per_point)
        custom_charges = [
            {
                "id": charge["id"],
                "name": charge["name"],
                "mode": charge["mode"],
                "amount": shares[charge["id"]][uid],
            }
            for charge in clean_custom
        ]
        adjustment = adjustments.get(month + "|" + uid) or {}
        if not isinstance(adjustment, dict):
            adjustment = {}
        try:
            fine = max(Decimal("0.00"), money(adjustment.get("fine", 0)))
            discount = max(Decimal("0.00"), money(adjustment.get("discount", 0)))
        except (InvalidOperation, TypeError, ValueError):
            fine = discount = Decimal("0.00")
        fixed = shares["fixed"][uid]
        water = shares["water"][uid]
        reserve = shares["reserve"][uid]
        extras = sum((charge["amount"] for charge in custom_charges), Decimal("0"))
        expected[uid] = {
            "user": uid,
            "name": user.get("name") or uid,
            "room": user.get("room") or "",
            "branch": user.get("branch") or "Mount Road",
            "accountType": user.get("type") or user.get("role") or "student",
            "individualFine": fine,
            "individualDiscount": discount,
            "fineReason": str(adjustment.get("fineReason") or ""),
            "discountReason": str(adjustment.get("discountReason") or ""),
            "customCharges": custom_charges,
            "base": {
                "totalPoints": points[uid],
                "pointsAmount": point_amount,
                "fixedCost": fixed,
                "waterCharges": water,
                "reservedFund": reserve,
                "customCharges": custom_charges,
                "fine": fine,
                "discount": discount,
                "grandTotal": money(point_amount + fixed + water + reserve + extras + fine - discount),
            },
            "fixedDiscount": fixed_discounts.get(uid, Decimal("0.00")),
            "entryDays": len(days[uid]),
            "missing": missing[uid],
            "perPoint": per_point,
        }
    return expected, total_points, total_expenses, per_point


def calculate_bill_bases(month, settings, all_users, entries, records, weekly_menu, today_menu, now=None, cancellations=None):
    return _calculate_bill_data(
        month, settings, all_users, entries, records, weekly_menu, today_menu, now, cancellations
    )[0]


def calculate_bill_summary(month, settings, all_users, entries, records, weekly_menu, today_menu, now=None, cancellations=None):
    expected, total_points, total_expenses, per_point = _calculate_bill_data(
        month, settings, all_users, entries, records, weekly_menu, today_menu, now, cancellations
    )
    missing_foods = sorted({
        food
        for bill in expected.values()
        for food in bill["missing"]
    })
    return {
        "totalUserPoints": total_points,
        "totalExpenses": total_expenses,
        "perPoint": per_point if total_points > 0 else None,
        "missingFoodPoints": missing_foods,
        "activeUsers": len(expected),
    }


def snapshot_calculation_mismatches(snapshot, expected):
    mismatches = []
    try:
        submitted_base = snapshot["base"]
        expected_base = expected["base"]
        if not isinstance(submitted_base, dict):
            return ["base"]
        for key in ("totalPoints", "pointsAmount", "fixedCost", "waterCharges", "reservedFund", "fine", "discount", "grandTotal"):
            try:
                if money(submitted_base[key]) != money(expected_base[key]):
                    mismatches.append("base." + key)
            except (KeyError, InvalidOperation, TypeError, ValueError):
                mismatches.append("base." + key)
        try:
            if money(snapshot.get("perPoint")) != money(expected.get("perPoint")):
                mismatches.append("perPoint")
        except (InvalidOperation, TypeError, ValueError):
            mismatches.append("perPoint")

        submitted_custom = submitted_base.get("customCharges") or []
        expected_custom = expected_base["customCharges"]
        if not isinstance(submitted_custom, list) or len(submitted_custom) != len(expected_custom):
            mismatches.append("base.customCharges")
        else:
            for index, (actual, wanted) in enumerate(zip(submitted_custom, expected_custom)):
                try:
                    same = (
                        isinstance(actual, dict)
                        and str(actual.get("id")) == wanted["id"]
                        and str(actual.get("name")) == wanted["name"]
                        and str(actual.get("mode") or "split") == wanted["mode"]
                        and money(actual.get("amount")) == money(wanted["amount"])
                    )
                except (KeyError, InvalidOperation, TypeError, ValueError):
                    same = False
                if not same:
                    mismatches.append("base.customCharges[" + str(index) + "]")

        mismatches.extend(_snapshot_base_mismatches(snapshot, expected_base))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        mismatches.append("calculation")
    return list(dict.fromkeys(mismatches))


def snapshot_matches_calculation(snapshot, expected):
    return not snapshot_calculation_mismatches(snapshot, expected)


def _snapshot_base_mismatches(snapshot, base):
    mismatches = []
    try:
        if not isinstance(base, dict):
            return ["base"]
        overrides = snapshot.get("overrides") or {}
        if not isinstance(overrides, dict):
            return ["overrides"]
        resolved = {}
        resolved["totalPoints"] = money(overrides["totalPoints"]) if "totalPoints" in overrides else money(base["totalPoints"])
        resolved["pointsAmount"] = money(resolved["totalPoints"] * money(snapshot.get("perPoint")))
        for field in ("fixedCost", "waterCharges", "reservedFund"):
            resolved[field] = money(overrides[field]) if field in overrides else money(base[field])
        for field in ("fine", "discount"):
            resolved[field] = money(overrides[field]) if field in overrides else money(base[field])

        base_custom = base.get("customCharges") or []
        submitted_custom = snapshot.get("customCharges") or []
        if not isinstance(base_custom, list) or not isinstance(submitted_custom, list):
            return ["customCharges"]
        if len(base_custom) != len(submitted_custom):
            mismatches.append("customCharges")

        custom_total = Decimal("0")
        for index, original in enumerate(base_custom):
            if index >= len(submitted_custom):
                break
            actual = submitted_custom[index]
            if not isinstance(actual, dict) or not isinstance(original, dict):
                mismatches.append("customCharges[" + str(index) + "]")
                continue
            if (
                str(actual.get("id")) != str(original.get("id"))
                or str(actual.get("name")) != str(original.get("name"))
                or str(actual.get("mode") or "split") != str(original.get("mode") or "split")
            ):
                mismatches.append("customCharges[" + str(index) + "]")
                continue
            field = "customCharge_" + re.sub(r"[^a-zA-Z0-9_-]", "_", str(original.get("id") or ""))
            fallback = money(original["amount"])
            amount = money(overrides[field]) if field in overrides else money(actual.get("amount"))
            if amount < 0 or (field not in overrides and amount != fallback):
                mismatches.append("customCharges[" + str(index) + "]")
            custom_total += amount

        for field in ("totalPoints", "pointsAmount", "fixedCost", "waterCharges", "reservedFund"):
            try:
                if money(snapshot[field]) != resolved[field]:
                    mismatches.append(field)
            except (KeyError, InvalidOperation, TypeError, ValueError):
                mismatches.append(field)
        for field, snapshot_field in (("fine", "individualFine"), ("discount", "individualDiscount")):
            try:
                if money(snapshot[snapshot_field]) != resolved[field]:
                    mismatches.append(snapshot_field)
            except (KeyError, InvalidOperation, TypeError, ValueError):
                mismatches.append(snapshot_field)

        computed_total = money(
            resolved["pointsAmount"] + resolved["fixedCost"] + resolved["waterCharges"]
            + resolved["reservedFund"] + custom_total + resolved["fine"] - resolved["discount"]
        )
        if "grandTotal" in overrides:
            computed_total = money(overrides["grandTotal"])
        submitted_total = money(snapshot.get("grandTotal", snapshot.get("finalTotal")))
        if submitted_total != computed_total:
            mismatches.append("grandTotal")
        if money(snapshot.get("finalTotal", submitted_total)) != submitted_total:
            mismatches.append("finalTotal")
    except (KeyError, InvalidOperation, TypeError, ValueError):
        mismatches.append("finalCalculation")
    return mismatches


def snapshot_matches_base(snapshot, base):
    try:
        if not isinstance(base, dict):
            return False
        overrides = snapshot.get("overrides") or {}
        if not isinstance(overrides, dict):
            return False
        # Admin can manually correct Total Points in the Excel bill editor.
        # Points in Rupees remains derived from that corrected value and the
        # authoritative monthly expense-based point rate.
        resolved = {}
        resolved["totalPoints"] = money(overrides["totalPoints"]) if "totalPoints" in overrides else money(base["totalPoints"])
        resolved["pointsAmount"] = money(resolved["totalPoints"] * money(snapshot.get("perPoint")))
        for field in ("fixedCost", "waterCharges", "reservedFund"):
            fallback = money(base[field])
            resolved[field] = money(overrides[field]) if field in overrides else fallback
        for field in ("fine", "discount"):
            fallback = money(base[field])
            resolved[field] = money(overrides[field]) if field in overrides else fallback

        base_custom = base.get("customCharges") or []
        submitted_custom = snapshot.get("customCharges") or []
        if not isinstance(base_custom, list) or not isinstance(submitted_custom, list):
            return False
        if len(base_custom) != len(submitted_custom):
            return False

        custom_total = Decimal("0")
        for actual, original in zip(submitted_custom, base_custom):
            if not isinstance(actual, dict) or not isinstance(original, dict):
                return False
            if (
                str(actual.get("id")) != str(original.get("id"))
                or str(actual.get("name")) != str(original.get("name"))
                or str(actual.get("mode") or "split") != str(original.get("mode") or "split")
            ):
                return False
            field = "customCharge_" + re.sub(r"[^a-zA-Z0-9_-]", "_", str(original.get("id") or ""))
            fallback = money(original["amount"])
            amount = money(overrides[field]) if field in overrides else money(actual.get("amount"))
            if amount < 0:
                return False
            if field not in overrides and amount != fallback:
                return False
            custom_total += amount

        for field in ("totalPoints", "pointsAmount", "fixedCost", "waterCharges", "reservedFund"):
            if money(snapshot[field]) != resolved[field]:
                return False
        if money(snapshot["individualFine"]) != resolved["fine"]:
            return False
        if money(snapshot["individualDiscount"]) != resolved["discount"]:
            return False

        computed_total = money(
            resolved["pointsAmount"] + resolved["fixedCost"] + resolved["waterCharges"]
            + resolved["reservedFund"] + custom_total + resolved["fine"] - resolved["discount"]
        )
        if "grandTotal" in overrides:
            computed_total = money(overrides["grandTotal"])
        submitted_total = money(snapshot.get("grandTotal", snapshot.get("finalTotal")))
        return (
            submitted_total == computed_total
            and money(snapshot.get("finalTotal", submitted_total)) == submitted_total
        )
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return False

# --- auth.py ---
from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone
import re
auth_bp = Blueprint('auth', __name__)
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    identity = str(data.get('uid') or '').strip()
    password = str(data.get('pw') or '')
    if not identity or not password:
        return jsonify({'success': False, 'message': 'Email/phone and password are required'}), 400

    user_data = get_user_by_identity(identity)
    if not user_data or not user_data.get('password_hash'):
        return jsonify({'success': False, 'message': 'Invalid email/phone or password'}), 401

    # Check password
    from werkzeug.security import check_password_hash
    if not check_password_hash(user_data['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid email/phone or password'}), 401

    if user_data.get('status') != 'active':
        return jsonify({'success': False, 'message': 'This user account is inactive'}), 401

    user_obj = User(user_data)
    if user_obj.role not in {'admin', 'student'}:
        return jsonify({'success': False, 'message': 'This account cannot sign in'}), 403

    login_user(user_obj)
    session['auth_version'] = int(user_data.get('auth_version') or 0)
    return jsonify({'success': True, 'user': user_obj.to_dict()})

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    name = str(data.get('name') or '').strip()
    room = str(data.get('room') or '').strip()
    phone = ''.join(filter(str.isdigit, str(data.get('phone') or '')))
    email = str(data.get('email') or '').strip().lower()
    password = str(data.get('password') or '')
    confirm = str(data.get('confirm') or '')

    if not all([name, room, phone, email, password]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if len(phone) != 10:
        return jsonify({'success': False, 'message': 'Enter a valid 10-digit phone number'}), 400

    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        return jsonify({'success': False, 'message': 'Enter a valid email address'}), 400

    if password != confirm:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    if registration_identity_exists(email, phone):
        return jsonify({'success': False, 'message': 'This email or phone is already registered or awaiting approval'}), 409

    # Create registration request
    reg_data = {
        'name': name,
        'room': room,
        'phone': phone,
        'email': email,
        'password': password
    }
    registration = create_registration(reg_data)
    submitted_at = datetime.now(timezone.utc)
    registration_id = getattr(registration, 'inserted_id', None)
    dedupe_key = (
        f"registration-{registration_id}"
        if registration_id is not None
        else f"registration-{email}-{submitted_at.isoformat()}"
    )
    get_collection('notifications').update_one(
        {'dedupeKey': dedupe_key},
        {
            '$setOnInsert': {
                'title': 'New enrollment request',
                'message': f"{name} submitted an enrollment request.",
                'date': 'Just now',
                'target': 'requests',
                'audience': 'admins',
                'dedupeKey': dedupe_key,
                'created_at': submitted_at,
            }
        },
        upsert=True,
    )

    return jsonify({'success': True, 'message': 'Registration submitted. Wait for admin approval.'})

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'success': True})

@auth_bp.route('/current-user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({'user': current_user.to_dict()})

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    old_password = str(data.get('oldPassword') or '')
    new_password = str(data.get('newPassword') or '')

    user_data = get_user(current_user.id)
    if not user_data or not user_data.get('password_hash'):
        return jsonify({'success': False, 'message': 'Account credentials are unavailable'}), 404
    from werkzeug.security import check_password_hash
    if not check_password_hash(user_data['password_hash'], old_password):
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    update_user(current_user.id, {'password': new_password})

    return jsonify({'success': True, 'message': 'Password changed successfully'})

# --- menu.py ---
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

menu_bp = Blueprint('menu', __name__)


def _today_weekly_menu():
    days = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    day = days[mess_now().date().weekday()]
    menu = next(
        (
            row for row in get_weekly_menu()
            if str(row.get('day') or '').strip().lower() == day.lower()
        ),
        {},
    )
    return {
        'breakfast': menu.get('b', ''),
        'lunch': menu.get('l', ''),
        'dinner': menu.get('d', ''),
    }


@menu_bp.route('/today', methods=['GET'])
def get_today_menu_route():
    return jsonify(_today_weekly_menu())


@menu_bp.route('/tomorrow', methods=['GET'])
def get_tomorrow_menu_route():
    days = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    target_date = tomorrow_date()
    day = days[target_date.weekday()]
    menu = next(
        (
            row for row in get_weekly_menu()
            if str(row.get('day') or '').strip().lower() == day.lower()
        ),
        {},
    )
    settings = get_settings()
    return jsonify({
        'success': True,
        'date': target_date.isoformat(),
        'breakfast': menu.get('b') or '',
        'lunch': menu.get('l') or '',
        'dinner': menu.get('d') or '',
        'cutoffTime': settings.get(
            'tomorrowCutoff',
            settings.get('cutoffTime', DEFAULT_TOMORROW_CUTOFF),
        ),
    })


@menu_bp.route('/today', methods=['PUT'])
@login_required
def update_today_menu():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    return jsonify({
        'success': False,
        'message': "Today's menu is derived from the weekly menu. Update the current weekday there instead.",
    }), 409


@menu_bp.route('/weekly', methods=['GET'])
def get_weekly_menu_route():
    days = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    known_days = {day.lower() for day in days}
    menus = get_weekly_menu()
    by_day = {
        str(menu.get('day') or '').strip().lower(): menu
        for menu in menus
        if isinstance(menu, dict)
    }
    result = [
        {
            'day': day,
            'b': by_day.get(day.lower(), {}).get('b', ''),
            'l': by_day.get(day.lower(), {}).get('l', ''),
            'd': by_day.get(day.lower(), {}).get('d', '')
        }
        for day in days
    ]
    result.extend(
        {
            'day': menu.get('day'),
            'b': menu.get('b', ''),
            'l': menu.get('l', ''),
            'd': menu.get('d', '')
        }
        for menu in menus
        if isinstance(menu, dict)
        and str(menu.get('day') or '').strip().lower() not in known_days
    )
    return jsonify(result)


@menu_bp.route('/weekly', methods=['PUT'])
@login_required
def update_weekly_menu():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json()
    save_weekly_menu(data)
    return jsonify({'success': True})

# --- settings.py ---
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from pymongo.errors import PyMongoError
import re
import math

settings_bp = Blueprint('settings', __name__)


def _validate_bill_config(value):
    if not isinstance(value, dict):
        return 'billConfig must be an object'
    if 'expenses' in value:
        expenses = value['expenses']
        if not isinstance(expenses, list) or len(expenses) > 100:
            return 'billConfig.expenses must be an array of at most 100 items'
        seen_ids = set()
        for expense in expenses:
            if not isinstance(expense, dict):
                return 'Every expense must be an object'
            expense_id = expense.get('id')
            name = expense.get('name')
            amount = expense.get('amount')
            if not isinstance(expense_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', expense_id):
                return 'Every expense must have a valid unique ID'
            if expense_id in seen_ids:
                return 'Expense IDs must be unique'
            seen_ids.add(expense_id)
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                return 'Every expense must have a name of at most 60 characters'
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                return 'Every expense amount must be a finite number greater than or equal to zero'
    if 'customCharges' in value:
        custom_charges = value['customCharges']
        if not isinstance(custom_charges, list):
            return 'billConfig.customCharges must be an array'
        seen_ids = set()
        for charge in custom_charges:
            if not isinstance(charge, dict):
                return 'Every custom charge must be an object'
            charge_id = charge.get('id')
            name = charge.get('name')
            amount = charge.get('amount')
            mode = charge.get('mode')
            if not isinstance(charge_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', charge_id):
                return 'Every custom charge must have a valid unique ID'
            if charge_id in seen_ids:
                return 'Custom charge IDs must be unique'
            seen_ids.add(charge_id)
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                return 'Every custom charge must have a name of at most 60 characters'
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not math.isfinite(amount)
                or amount < 0
            ):
                return 'Every custom charge amount must be a finite number greater than or equal to zero'
            if mode not in ('split', 'each'):
                return 'Every custom charge mode must be split or each'
    return None


def _validate_food_points(value):
    if not isinstance(value, dict) or len(value) > 500:
        return 'foodPoints must be an object containing at most 500 food records'
    for key, food in value.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or len(key) > 120
            or not isinstance(food, dict)
        ):
            return 'Each food point must have a valid food key and object'
        name = food.get('name')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            return 'Each food point must include a food name of at most 120 characters'
        normalized_name = re.sub(r'\s+', ' ', name.strip()).lower()
        if normalized_name != key:
            return 'Food-point keys must match the normalized food name'
        for field in ('price', 'point'):
            amount = food.get(field, '')
            if amount in ('', None):
                continue
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not math.isfinite(amount)
                or amount < 0
            ):
                return f'{field} for {name.strip()} must be a finite number greater than or equal to zero'
    return None


@settings_bp.route('/', methods=['GET'])
@login_required
def get_settings_route():
    try:
        settings = get_settings()
    except (PyMongoError, RuntimeError):
        current_app.logger.error("Settings read failed.")
        return jsonify({
            'success': False,
            'message': 'Settings could not be loaded from the database.',
        }), 503
    if current_user.role != 'admin':
        student_keys = {
            'foodPoints',
            'menuSnapshots',
            'tomorrowCutoff',
            'cutoffTime',
            'breakfastOpen',
            'breakfastClose',
            'lunchOpen',
            'lunchClose',
            'dinnerOpen',
            'dinnerClose',
        }
        settings = {
            key: value
            for key, value in settings.items()
            if key in student_keys
        }
    return jsonify({'settings': settings})


@settings_bp.route('/food-points', methods=['PATCH'])
@login_required
def update_food_points_route():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400

    food_points = data.get('foodPoints')
    if not isinstance(food_points, dict):
        return jsonify({'success': False, 'message': 'foodPoints must be an object'}), 400

    changed_key = data.get('changedKey')
    if changed_key is not None:
        if not isinstance(changed_key, str) or changed_key not in food_points:
            return jsonify({'success': False, 'message': 'changedKey must identify a food record in foodPoints'}), 400
        food_points = {changed_key: food_points[changed_key]}

    validation_error = _validate_food_points(food_points)
    if validation_error:
        return jsonify({'success': False, 'message': validation_error}), 400

    saved = update_food_points(food_points)
    return jsonify({'success': True, 'foodPoints': saved})


@settings_bp.route('/', methods=['POST'])
@login_required
def save_settings_route():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({'success': False, 'message': 'A settings object is required'}), 400
    if 'billConfig' in data:
        validation_error = _validate_bill_config(data['billConfig'])
        if validation_error:
            return jsonify({'success': False, 'message': validation_error}), 400
    if 'foodPoints' in data:
        validation_error = _validate_food_points(data['foodPoints'])
        if validation_error:
            return jsonify({'success': False, 'message': validation_error}), 400
    for key in (
        'tomorrowCutoff',
        'cutoffTime',
        'breakfastOpen',
        'breakfastClose',
        'lunchOpen',
        'lunchClose',
        'dinnerOpen',
        'dinnerClose',
    ):
        if key in data and (
            not isinstance(data[key], str)
            or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', data[key])
        ):
            return jsonify({'success': False, 'message': f'{key} must use HH:MM format'}), 400
    food_points = data.pop('foodPoints', None)
    try:
        if food_points is not None:
            update_food_points(food_points)
        if data:
            save_settings(data)
        settings = get_settings()
    except (PyMongoError, RuntimeError):
        current_app.logger.error("Settings persistence or verification failed.")
        return jsonify({
            'success': False,
            'message': 'Settings could not be saved and verified.',
        }), 503

    if any(settings.get(key) != value for key, value in data.items()):
        current_app.logger.error("Settings persistence read-back verification failed.")
        return jsonify({
            'success': False,
            'message': 'Settings could not be saved and verified.',
        }), 503
    return jsonify({'success': True, 'settings': settings})

# --- notifications.py ---
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from bson import ObjectId

notifications_bp = Blueprint('notifications', __name__)


def _notification_visible_to_current_user(notification):
    audience = notification.get('audience')
    user_id = str(notification.get('userId') or '')
    if current_user.role == 'admin':
        if audience == 'admins':
            return not user_id or user_id == current_user.id
        return audience in (None, '', 'all', 'users', 'students') and not user_id
    if audience == 'admins':
        return False
    if audience in (None, '', 'all', 'users', 'students'):
        return not user_id or user_id == current_user.id
    return audience == 'user' and user_id == current_user.id


def _visible_notifications(target=None):
    notifications = get_notifications()
    visible = []
    for notification in notifications:
        if not _notification_visible_to_current_user(notification):
            continue
        if current_user.id in (notification.get('dismissed_by') or []):
            continue
        if target is not None and notification.get('target') != target:
            continue
        visible.append(notification)
    return visible


@notifications_bp.route('/', methods=['GET'])
@login_required
def get_notifications_route():
    notifications = _visible_notifications()
    result = []
    for notif in notifications:
        notif_dict = dict(notif)
        audience = notif_dict.get('audience')
        date_str = notif_dict.get('date')
        if not date_str and 'created_at' in notif_dict:
            if isinstance(notif_dict['created_at'], datetime):
                date_str = notif_dict['created_at'].strftime('%Y-%m-%d %H:%M')
            else:
                date_str = str(notif_dict['created_at'])
        read_by = notif_dict.get('read_by', [])
        if not isinstance(read_by, list):
            read_by = []
        result.append({
            'id': str(notif_dict.get('_id', '')),
            't': notif_dict.get('title'),
            'm': notif_dict.get('message'),
            'd': date_str or 'Just now',
            'read': current_user.id in read_by,
            'target': notif_dict.get('target'),
            'audience': audience,
            'userId': notif_dict.get('userId'),
            'dedupeKey': notif_dict.get('dedupeKey'),
            'createdAt': (
                notif_dict['created_at'].isoformat()
                if hasattr(notif_dict.get('created_at'), 'isoformat')
                else str(notif_dict.get('created_at') or '')
            ),
        })
    return jsonify({'notifications': result})

@notifications_bp.route('/', methods=['POST'])
@login_required
def send_notification():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    title = str(data.get('title') or '').strip()
    message = str(data.get('message') or '').strip()
    if not title or not message:
        return jsonify({'success': False, 'message': 'Notification title and message are required'}), 400
    notif_data = {
        'title': title,
        'message': message,
        'date': 'Just now',
        'target': data.get('target'),
        'audience': data.get('audience'),
        'userId': data.get('userId'),
        'dedupeKey': data.get('dedupeKey'),
    }
    if notif_data['dedupeKey']:
        get_collection('notifications').update_one(
            {'dedupeKey': notif_data['dedupeKey']},
            {
                '$setOnInsert': {**notif_data, 'created_at': datetime.utcnow()},
            },
            upsert=True,
        )
    else:
        create_notification(notif_data)
    return jsonify({'success': True, 'notification': notif_data})

@notifications_bp.route('/<notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    if not ObjectId.is_valid(notif_id):
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    collection = get_collection('notifications')
    notification = collection.find_one({'_id': ObjectId(notif_id)})
    if (
        not notification
        or not _notification_visible_to_current_user(notification)
        or current_user.id in (notification.get('dismissed_by') or [])
    ):
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    result = collection.update_one(
        {
            '_id': ObjectId(notif_id),
            'dismissed_by': {'$ne': current_user.id},
        },
        {'$addToSet': {'read_by': current_user.id}},
    )
    if not result.matched_count:
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    return jsonify({'success': True})


@notifications_bp.route('/read-all', methods=['POST'])
@login_required
def mark_visible_notifications_read():
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    target = data.get('target')
    if target is not None and (
        not isinstance(target, str) or not target.strip() or len(target) > 80
    ):
        return jsonify({'success': False, 'message': 'A valid notification target is required'}), 400
    notifications = _visible_notifications(target.strip() if target else None)
    ids = [item['_id'] for item in notifications if item.get('_id') is not None]
    if ids:
        get_collection('notifications').update_many(
            {'_id': {'$in': ids}, 'dismissed_by': {'$ne': current_user.id}},
            {'$addToSet': {'read_by': current_user.id}},
        )
    return jsonify({'success': True, 'updated': len(ids)})


@notifications_bp.route('/clear', methods=['POST'])
@login_required
def clear_visible_notifications():
    notifications = _visible_notifications()
    ids = [item['_id'] for item in notifications if item.get('_id') is not None]
    if ids:
        get_collection('notifications').update_many(
            {'_id': {'$in': ids}, 'dismissed_by': {'$ne': current_user.id}},
            {
                '$addToSet': {
                    'dismissed_by': current_user.id,
                    'read_by': current_user.id,
                }
            },
        )
    return jsonify({'success': True, 'cleared': len(ids)})

# --- feedback.py ---
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone

feedback_bp = Blueprint('feedback', __name__)

@feedback_bp.route('/', methods=['GET'])
@login_required
def get_feedback_route():
    feedback = get_feedback(
        None if current_user.role == 'admin' else current_user.id
    )
    result = []
    for fb in feedback:
        fb_dict = dict(fb)
        if '_id' in fb_dict:
            fb_dict['_id'] = str(fb_dict['_id'])
        result.append(fb_dict)
    return jsonify({'feedback': result})

@feedback_bp.route('/', methods=['POST'])
@login_required
def submit_feedback_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    meal = data.get('meal')
    rating = data.get('rating', 0)
    comment = data.get('comment', '')
    if meal not in {'breakfast', 'lunch', 'dinner'}:
        return jsonify({'success': False, 'message': 'Select a valid meal'}), 400
    if isinstance(rating, bool) or not isinstance(rating, int) or not 0 <= rating <= 5:
        return jsonify({'success': False, 'message': 'Rating must be a whole number from 0 to 5'}), 400
    if not isinstance(comment, str) or len(comment) > 2000:
        return jsonify({'success': False, 'message': 'Feedback must be text of 2000 characters or fewer'}), 400
    fb_data = {
        'user_id': current_user.id,
        'name': current_user.name,
        'room': current_user.room,
        'meal': meal,
        'food': str(data.get('food') or '')[:200],
        'rating': rating,
        'comment': comment.strip(),
        'date': 'Just now'
    }
    submitted_at = datetime.now(timezone.utc)
    save_feedback({**fb_data, 'submitted_at': submitted_at})
    preview = comment.strip().replace('\n', ' ')[:140]
    subject = f"{meal.title()}" + (f" · {fb_data['food']}" if fb_data['food'] else "")
    message = f"{current_user.name} submitted {subject} feedback"
    if preview:
        message += f": {preview}"
    get_collection('notifications').update_one(
        {
            'dedupeKey': (
                f"feedback-{current_user.id}-{meal}-"
                f"{submitted_at.isoformat()}"
            )
        },
        {
            '$setOnInsert': {
                'title': 'New student feedback',
                'message': message,
                'date': submitted_at.strftime('%Y-%m-%d %H:%M UTC'),
                'target': 'feedback',
                'audience': 'admins',
                'userId': None,
                'dedupeKey': (
                    f"feedback-{current_user.id}-{meal}-"
                    f"{submitted_at.isoformat()}"
                ),
                'created_at': submitted_at,
            }
        },
        upsert=True,
    )
    return jsonify({'success': True, 'feedback': fb_data})

# --- users.py ---
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from bson import ObjectId
import re

users_bp = Blueprint('users', __name__)


@users_bp.route('/admin-presence', methods=['POST', 'DELETE'])
@login_required
def admin_presence_route():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    viewer_id = data.get('viewerId')
    if not isinstance(viewer_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', viewer_id):
        return jsonify({'success': False, 'message': 'A valid viewerId is required'}), 400

    if request.method == 'DELETE':
        remove_admin_presence(viewer_id, current_user.id)
        return jsonify({'success': True})

    return jsonify({
        'success': True,
        'activeAdmins': update_admin_presence(viewer_id, current_user.id),
    })


@users_bp.route('/', methods=['GET'])
@login_required
def get_users_route():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    users = get_all_users()
    # Convert ObjectId to string and remove password_hash
    result = []
    for user in users:
        user_dict = dict(user)
        user_dict.pop('password_hash', None)
        user_dict.pop('password', None)
        if '_id' in user_dict:
            user_dict['_id'] = str(user_dict['_id'])
        result.append(user_dict)
    return jsonify({'users': sorted(result, key=room_record_sort_key)})

@users_bp.route('/', methods=['POST'])
@login_required
def create_user_route():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    def text_field(name):
        value = data.get(name, '')
        return value.strip() if isinstance(value, str) else ''

    user_data = {
        'id': text_field('id').upper(),
        'name': text_field('name'),
        'room': text_field('room'),
        'phone': text_field('phone'),
        'email': text_field('email').lower(),
        'password': data.get('password', '') if isinstance(data.get('password'), str) else '',
        'role': 'student',
        'status': 'active'
    }
    if not all([user_data['id'], user_data['name'], user_data['room'], user_data['password']]):
        return jsonify({'success': False, 'message': 'ID, name, room, and password are required'}), 400
    if user_data['email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', user_data['email']):
        return jsonify({'success': False, 'message': 'Enter a valid email address'}), 400
    if user_data['phone'] and len(re.sub(r'\D', '', user_data['phone'])) != 10:
        return jsonify({'success': False, 'message': 'Enter a valid 10-digit phone number'}), 400
    if user_data['phone']:
        user_data['phone'] = re.sub(r'\D', '', user_data['phone'])
    if len(user_data['password']) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    if (
        get_user_by_identity(user_data['id'])
        or (user_data['email'] and registration_identity_exists(user_data['email'], ''))
        or (user_data['phone'] and registration_identity_exists('', user_data['phone']))
    ):
        return jsonify({'success': False, 'message': 'This user ID, email, or phone is already registered'}), 409
    create_user(user_data)
    return jsonify({
        'success': True,
        'user': {
            key: user_data[key]
            for key in ('id', 'name', 'room', 'phone', 'email', 'role', 'status')
        },
    }), 201

@users_bp.route('/<user_id>', methods=['PUT'])
@login_required
def update_user_route(user_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    user = get_user(user_id.upper())
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    updates = {}
    for field in ('name', 'room', 'phone', 'email'):
        if field in data:
            if not isinstance(data[field], str):
                return jsonify({'success': False, 'message': f'{field} must be text'}), 400
            updates[field] = data[field].strip()
    if 'phone' in updates and updates['phone']:
        updates['phone'] = re.sub(r'\D', '', updates['phone'])
        if len(updates['phone']) != 10:
            return jsonify({'success': False, 'message': 'Enter a valid 10-digit phone number'}), 400
    if 'email' in updates:
        updates['email'] = updates['email'].lower()
        if updates['email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', updates['email']):
            return jsonify({'success': False, 'message': 'Enter a valid email address'}), 400
    if registration_identity_exists(
        updates.get('email', ''),
        updates.get('phone', ''),
        exclude_user_id=user_id.upper(),
    ):
        return jsonify({'success': False, 'message': 'This email or phone is already registered'}), 409
    if 'status' in data:
        if not isinstance(data['status'], str) or data['status'] not in {'active', 'inactive'}:
            return jsonify({'success': False, 'message': 'Status must be active or inactive'}), 400
        updates['status'] = data['status']
    if 'password' in data:
        if not isinstance(data['password'], str) or len(data['password']) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        updates['password'] = data['password']

    update_user(user_id.upper(), updates)
    return jsonify({'success': True})

@users_bp.route('/<user_id>', methods=['DELETE'])
@login_required
def delete_user_route(user_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    user = get_user(user_id.upper())
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    delete_user(user_id.upper())
    return jsonify({'success': True})

@users_bp.route('/<user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    user = get_user(user_id.upper())
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    new_status = 'inactive' if user.get('status') == 'active' else 'active'
    update_user(user_id.upper(), {'status': new_status})
    return jsonify({'success': True, 'user': {'id': user_id, 'status': new_status}})

@users_bp.route('/registrations', methods=['GET'])
@login_required
def get_registrations():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    regs = get_pending_registrations()
    result = []
    for reg in regs:
        reg_dict = dict(reg)
        reg_dict.pop('password_hash', None)
        reg_dict.pop('password', None)
        if '_id' in reg_dict:
            reg_dict['_id'] = str(reg_dict['_id'])
        result.append(reg_dict)
    return jsonify({'registrations': result})

@users_bp.route('/registrations/<reg_id>/approve', methods=['POST'])
@login_required
def approve_registration(reg_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not ObjectId.is_valid(reg_id):
        return jsonify({'success': False, 'message': 'Registration not found'}), 404
    reg = get_collection('registration_requests').find_one({'_id': ObjectId(reg_id)})
    if not reg or reg.get('status') != 'pending':
        return jsonify({'success': False, 'message': 'Registration not found'}), 404

    base_id = 'STU' + reg_id[-8:].upper()
    user_id = base_id
    suffix = 2
    while get_user(user_id):
        user_id = f'{base_id}{suffix}'
        suffix += 1
    user_data = {
        'id': user_id,
        'name': reg['name'],
        'room': reg['room'],
        'phone': reg['phone'],
        'email': reg['email'],
        'password_hash': reg['password_hash'],
        'role': 'student',
        'status': 'active'
    }
    get_collection('users').insert_one(user_data)
    update_registration(ObjectId(reg_id), {'status': 'approved'})

    safe_user = {key: value for key, value in user_data.items() if key != 'password_hash'}
    return jsonify({'success': True, 'user': safe_user})

@users_bp.route('/registrations/<reg_id>/reject', methods=['POST'])
@login_required
def reject_registration(reg_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not ObjectId.is_valid(reg_id):
        return jsonify({'success': False, 'message': 'Registration not found'}), 404
    reg = get_collection('registration_requests').find_one({'_id': ObjectId(reg_id), 'status': 'pending'})
    if not reg:
        return jsonify({'success': False, 'message': 'Registration not found'}), 404
    update_registration(ObjectId(reg_id), {'status': 'rejected'})
    return jsonify({'success': True})

# --- entries.py ---
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from pymongo.errors import PyMongoError
import re
from bson import ObjectId

entries_bp = Blueprint('entries', __name__)


def load_approved_no_food_map(date_value=None, month=None):
    try:
        return get_approved_no_food_map(date_value=date_value, month=month), None
    except (KeyError, RuntimeError, PyMongoError) as exc:
        current_app.logger.error(
            "Could not load approved No Food records (%s).",
            type(exc).__name__,
        )
        return None, (jsonify({
            'success': False,
            'message': 'Approved No Food records could not be loaded.',
        }), 503)


def serialize_entry(entry):
    result = dict(entry)
    if '_id' in result:
        result['_id'] = str(result['_id'])
    return result


def latest_entries_by_user_date(entries):
    """Keep the most recently updated entry for each user and date."""
    latest = []
    seen = set()
    for entry in entries:
        user_id = str(entry.get('user_id') or entry.get('user') or '').strip().upper()
        date_value = str(entry.get('date') or '')
        if not user_id or not date_value:
            latest.append(entry)
            continue

        key = (user_id, date_value)
        if key in seen:
            continue
        seen.add(key)
        latest.append(entry)
    return latest


def apply_approved_no_food(entry, approved):
    """Expose approved no-food meals as zero in entry views with an audit marker."""
    result = dict(entry)
    user_id = str(result.get("user_id") or result.get("user") or "").upper()
    date_value = str(result.get("date") or "")[:10]
    no_food_meals = dict(result.get("noFoodMeals") or {})
    for short, field in (("b", "breakfast"), ("l", "lunch"), ("d", "dinner")):
        request = approved.get((user_id, date_value, short))
        existing_marker = no_food_meals.get(short)
        if (
            request is None
            and isinstance(existing_marker, dict)
            and existing_marker.get("review_state")
        ):
            no_food_meals.pop(short, None)
        if not request:
            continue
        result.setdefault("scheduled_" + field, result.get(field, result.get(short, 0)))
        result[field] = 0
        result[short] = 0
        no_food_meals[short] = {
            "status": "approved",
            "request_id": str(request.get("_id") or request.get("request_id") or ""),
            "dish_name": request.get("dish_name") or "",
            "approved_at": request.get("reviewed_at") or request.get("approved_at"),
        }
    if no_food_meals:
        result["noFoodMeals"] = no_food_meals
    else:
        result.pop("noFoodMeals", None)
    return result


def valid_quantities(data, partial=False):
    quantities = {}
    for field in ('breakfast', 'lunch', 'dinner'):
        short = {'breakfast': 'b', 'lunch': 'l', 'dinner': 'd'}[field]
        if partial and field not in data and short not in data:
            continue
        value = data.get(field, data.get(short, 0))
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 99:
            return None
        quantities[field] = value
    return quantities


@entries_bp.route('/', methods=['GET'])
@login_required
def get_entries_route():
    date_str = request.args.get('date')
    month_str = request.args.get('month')
    target_date = None
    if date_str and month_str:
        return jsonify({'success': False, 'message': 'Specify either date or month, not both'}), 400
    if month_str:
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month_str):
            return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400
        target_pattern = '^' + re.escape(month_str) + '-'
    elif date_str:
        try:
            target_date = parse_entry_date(date_str).isoformat()
        except ValueError:
            return jsonify({'success': False, 'message': 'Date must use YYYY-MM-DD format'}), 400
        target_pattern = '^' + re.escape(target_date) + '$'
    else:
        target_date = mess_now().date().isoformat()
        target_pattern = '^' + re.escape(target_date) + '$'

    query = {'date': {'$regex': target_pattern}}
    if current_user.role != 'admin':
        query['user_id'] = current_user.id
    cursor = get_collection('mess_entries').find(query).sort([
        ('updated_at', -1),
        ('_id', -1),
    ])
    raw_entries = list(cursor)
    latest = latest_entries_by_user_date(raw_entries)

    # Log counts only; never print student details or credentials.
    current_app.logger.debug(
        "GET /api/entries: date=%s month=%s matched=%d latest=%d",
        target_date, month_str, len(raw_entries), len(latest),
    )

    approved, error_response = load_approved_no_food_map(
        date_value=target_date if not month_str else None,
        month=month_str,
    )
    if error_response:
        return error_response
    latest = [apply_approved_no_food(entry, approved) for entry in latest]
    
    users_by_id = {}
    for entry in latest:
        user_id = str(entry.get('user_id') or entry.get('user') or '').upper()
        if user_id and user_id not in users_by_id:
            users_by_id[user_id] = get_user(user_id) or {}
        entry['user_name'] = users_by_id.get(user_id, {}).get('name') or user_id
    if not month_str:
        settings = get_settings()
        local_now = mess_now()
        try:
            target_cooking_date = cooking_date(settings, local_now).isoformat()
        except ValueError as error:
            current_app.logger.error("Invalid configured entry cutoff (%s).", type(error).__name__)
            return jsonify({
                'success': False,
                'message': 'The configured entry cutoff is invalid.',
            }), 503
        return jsonify({
            'entries': [serialize_entry(entry) for entry in latest],
            'cancellations': list_cancellations(date_value=target_date),
            'server_date': local_now.date().isoformat(),
            'cooking_date': target_cooking_date,
        })

    cancelled = {
        (item.get('date'), item.get('meal_type'))
        for item in list_cancellations(month=month_str)
    }
    monthly_by_user = {}
    summary = {'breakfast': 0, 'lunch': 0, 'dinner': 0, 'total': 0}
    for entry in latest:
        user_id = str(entry.get('user_id') or entry.get('user') or '').upper()
        monthly = monthly_by_user.setdefault(user_id, {
            'user_id': user_id,
            'user': user_id,
            'user_name': entry.get('user_name') or user_id,
            'room': entry.get('room') or '',
            'date': month_str,
            'breakfast': 0,
            'lunch': 0,
            'dinner': 0,
        })
        for field, short in (('breakfast', 'b'), ('lunch', 'l'), ('dinner', 'd')):
            if (entry.get('date'), short) not in cancelled:
                value = quantity(entry.get(field, entry.get(short, 0)))
                monthly[field] += value
                summary[field] += value
    summary['total'] = summary['breakfast'] + summary['lunch'] + summary['dinner']
    grouped = sorted(monthly_by_user.values(), key=room_record_sort_key)
    for row in grouped:
        row['total'] = row['breakfast'] + row['lunch'] + row['dinner']

    try:
        page = max(1, int(request.args.get('page', '1')))
        per_page = min(200, max(1, int(request.args.get('per_page', '100'))))
    except ValueError:
        return jsonify({'success': False, 'message': 'page and per_page must be integers'}), 400
    start = (page - 1) * per_page
    page_entries = grouped[start:start + per_page]
    return jsonify({
        'entries': [serialize_entry(entry) for entry in page_entries],
        'summary': summary,
        'total': len(grouped),
        'page': page,
        'perPage': per_page,
        'pages': (len(grouped) + per_page - 1) // per_page,
        'cancellations': list_cancellations(month=month_str),
    })

@entries_bp.route('/tomorrow', methods=['GET'])
@login_required
def get_tomorrow_entries():
    tomorrow = tomorrow_date().isoformat()
    query = {'date': {'$regex': '^' + re.escape(tomorrow)}}
    if current_user.role != 'admin':
        query['user_id'] = current_user.id
    entries = get_collection('mess_entries').find(query).sort([
        ('updated_at', -1),
        ('_id', -1),
    ])
    approved, error_response = load_approved_no_food_map(date_value=tomorrow)
    if error_response:
        return error_response
    return jsonify({
        'entries': [
            serialize_entry(apply_approved_no_food(entry, approved))
            for entry in latest_entries_by_user_date(entries)
        ]
    })

@entries_bp.route('/history', methods=['GET'])
@login_required
def get_entry_history():
    query = {} if current_user.role == 'admin' else {'user_id': current_user.id}
    entries = get_collection('mess_entries').find(query).sort([
        ('date', -1),
        ('updated_at', -1),
        ('_id', -1),
    ])
    
    raw_entries = list(entries)
    approved, error_response = load_approved_no_food_map()
    if error_response:
        return error_response
    latest = latest_entries_by_user_date(raw_entries)
    current_app.logger.debug(
        "GET /api/entries/history matched=%d latest=%d",
        len(raw_entries),
        len(latest),
    )
    
    return jsonify({
        'entries': [
            serialize_entry(apply_approved_no_food(entry, approved))
            for entry in latest
        ]
    })

@entries_bp.route('/', methods=['POST'])
@login_required
def submit_entry():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400

    quantities = valid_quantities(data)
    if quantities is None:
        return jsonify({'success': False, 'message': 'Meal quantities must be whole numbers from 0 to 99'}), 400

    if current_user.role == 'admin':
        user_id = str(data.get('user_id') or '').strip().upper()
        date_value = str(data.get('date') or '').strip()
        if not user_id or not date_value:
            return jsonify({'success': False, 'message': 'Student ID and date are required'}), 400
        try:
            parse_entry_date(date_value)
        except ValueError:
            return jsonify({'success': False, 'message': 'Date must use YYYY-MM-DD format'}), 400
        user = get_user(user_id)
        if not user or user.get('role', 'student') != 'student':
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        entry_data = {
            'user_id': user_id,
            'room': user.get('room', ''),
            'date': date_value,
            **quantities,
            'adminApproved': True,
        }
    else:
        settings = get_settings()
        try:
            target_date = parse_entry_date(data['date']) if 'date' in data else tomorrow_date()
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 400
        expected_date = tomorrow_date()
        if target_date != expected_date:
            return jsonify({
                'success': False,
                'message': 'Students may submit only tomorrow’s mess entry.',
            }), 400
        try:
            is_closed = tomorrow_entry_is_closed(settings)
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 503
        if is_closed:
            return jsonify({
                'success': False,
                'message': 'The cutoff for tomorrow’s mess entry has passed.',
            }), 403

        entry_data = {
            'user_id': current_user.id,
            'room': current_user.room,
            'date': target_date.isoformat(),
            **quantities,
        }

    no_food_collection = get_collection("no_food_requests")
    for field, short in (("breakfast", "b"), ("lunch", "l"), ("dinner", "d")):
        if quantities[field] <= 0:
            continue
        no_food = no_food_collection.find_one({
            "user_id": entry_data["user_id"],
            "date": entry_data["date"],
            "meal": short,
            "status": {"$in": ["pending", "approved"]},
        })
        if no_food:
            return jsonify({
                "success": False,
                "message": f"{field.capitalize()} has a pending or approved no-food request.",
            }), 409

    for field, short in (('breakfast', 'b'), ('lunch', 'l'), ('dinner', 'd')):
        if quantities[field] > 0 and is_meal_cancelled(entry_data['date'], short):
            return jsonify({
                'success': False,
                'message': f'{field.capitalize()} is cancelled for this date.',
            }), 409

    result = create_entry(entry_data)
    recalculate_existing_meal_record(
        entry_data["user_id"],
        entry_data["date"],
        entry_data,
    )
    if current_user.role != 'admin':
        from datetime import datetime, timezone
        get_collection('notifications').update_one(
            {'dedupeKey': f"entry-{current_user.id}-{entry_data['date']}"},
            {
                '$setOnInsert': {
                    'title': 'New mess entry',
                    'message': f"{current_user.name or current_user.id} submitted a mess entry.",
                    'date': 'Just now',
                    'target': 'entries',
                    'audience': 'admins',
                    'dedupeKey': f"entry-{current_user.id}-{entry_data['date']}",
                    'created_at': datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    return jsonify({
        'success': True,
        'entry': {**entry_data, '_id': str(result.upserted_id) if result.upserted_id else None},
    })

@entries_bp.route('/<entry_id>', methods=['PUT'])
@login_required
def update_entry_route(entry_id):
    if not ObjectId.is_valid(entry_id):
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    entry = get_collection('mess_entries').find_one({'_id': ObjectId(entry_id)})
    if not entry or (current_user.role != 'admin' and entry.get('user_id') != current_user.id):
        return jsonify({'success': False, 'message': 'Entry not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    quantities = valid_quantities(data, partial=True)
    if quantities is None or not quantities:
        return jsonify({'success': False, 'message': 'Meal quantities must be whole numbers from 0 to 99'}), 400
    if current_user.role != 'admin':
        try:
            entry_date = parse_entry_date(entry.get('date'))
            is_closed = tomorrow_entry_is_closed(get_settings())
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 503
        if entry_date != tomorrow_date() or is_closed:
            return jsonify({
                'success': False,
                'message': 'This mess entry can no longer be edited.',
            }), 403

    for field, short in (('breakfast', 'b'), ('lunch', 'l'), ('dinner', 'd')):
        if (
            field in quantities
            and quantities[field] > 0
            and is_meal_cancelled(str(entry.get('date') or ''), short)
        ):
            return jsonify({
                'success': False,
                'message': f'{field.capitalize()} is cancelled for this date.',
            }), 409

    no_food_collection = get_collection("no_food_requests")
    for field, short in (("breakfast", "b"), ("lunch", "l"), ("dinner", "d")):
        if field not in quantities or quantities[field] <= 0:
            continue
        no_food = no_food_collection.find_one({
            "user_id": entry.get("user_id"),
            "date": entry.get("date"),
            "meal": short,
            "status": {"$in": ["pending", "approved"]},
        })
        if no_food:
            return jsonify({
                "success": False,
                "message": f"{field.capitalize()} has a pending or approved no-food request.",
            }), 409

    update_entry(ObjectId(entry_id), quantities)
    updated_entry = dict(entry)
    updated_entry.update(quantities)
    recalculate_existing_meal_record(
        str(entry.get("user_id") or ""),
        str(entry.get("date") or ""),
        updated_entry,
    )
    return jsonify({'success': True})

@entries_bp.route('/<entry_id>', methods=['DELETE'])
@login_required
def delete_entry_route(entry_id):
    if not ObjectId.is_valid(entry_id):
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    entry = get_collection('mess_entries').find_one({'_id': ObjectId(entry_id)})
    if not entry or (current_user.role != 'admin' and entry.get('user_id') != current_user.id):
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    if current_user.role != 'admin':
        try:
            entry_date = parse_entry_date(entry.get('date'))
            is_closed = tomorrow_entry_is_closed(get_settings())
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 503
        if entry_date != tomorrow_date() or is_closed:
            return jsonify({
                'success': False,
                'message': 'This mess entry can no longer be cancelled.',
            }), 403

    delete_entry(ObjectId(entry_id))
    recalculate_existing_meal_record(
        str(entry.get("user_id") or ""),
        str(entry.get("date") or ""),
        {},
    )
    return jsonify({'success': True})

# --- bills.py ---
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from bson import ObjectId
from pymongo.errors import PyMongoError

bills_bp = Blueprint('bills', __name__)


def valid_bill_snapshot(item):
    if not isinstance(item, dict):
        return None
    user_id = str(item.get('user_id') or item.get('user') or '').strip().upper()
    month = str(item.get('billing_month') or item.get('billingMonth') or item.get('month') or '').strip()
    total = item.get('grandTotal', item.get('finalTotal', item.get('final_total', item.get('amount'))))
    if not user_id or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return None
    try:
        total_value = _money(total)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if total_value < 0:
        return None

    document = {
        key: value for key, value in item.items()
        if key not in {'_id', 'password', 'password_hash', 'user_id', 'billing_month', 'created_at'}
    }
    document['user_id'] = user_id
    document['billing_month'] = month
    document['grandTotal'] = float(total_value)
    document['finalTotal'] = float(total_value)
    document['final_total'] = float(total_value)
    document['amount'] = float(total_value)
    document['updated_at'] = datetime.now(timezone.utc)

    if int(item.get('calcVersion') or 0) >= 3:
        fields = (
            'totalPoints', 'perPoint', 'pointsAmount', 'fixedCost',
            'waterCharges', 'reservedFund', 'individualFine',
            'individualDiscount', 'grandTotal',
        )
        try:
            amounts = {key: _money(item[key]) for key in fields}
            if any(value < 0 for key, value in amounts.items() if key != 'individualDiscount'):
                return None
            if amounts['individualDiscount'] < 0:
                return None
            overrides = item.get('overrides') or {}
            if not isinstance(overrides, dict):
                return None
            # Admin may explicitly correct monthly Total Points in the bill
            # editor. The rupee amount must still match the saved point rate;
            # it is derived, not an independent manual override.
            expected_points = _money(amounts['totalPoints'] * amounts['perPoint'])
            if expected_points != amounts['pointsAmount']:
                return None
            if 'grandTotal' not in overrides:
                custom_total = Decimal('0.00')
                charges = item.get('customCharges') or []
                if not isinstance(charges, list):
                    return None
                for charge in charges:
                    if not isinstance(charge, dict):
                        return None
                    amount = _money(charge.get('amount'))
                    if amount < 0:
                        return None
                    custom_total += amount
                expected_total = _money(
                    amounts['pointsAmount'] + amounts['fixedCost']
                    + amounts['waterCharges'] + amounts['reservedFund']
                    + custom_total + amounts['individualFine']
                    - amounts['individualDiscount']
                )
                if expected_total != amounts['grandTotal']:
                    return None
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return None
        if _money(item.get('finalTotal', item.get('final_total', total))) != amounts['grandTotal']:
            return None
    return document


def _money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError('Money values must be numeric.')
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError('Money values must be finite.')
    return parsed.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _validated_bill_drafts(items, month):
    if not isinstance(items, list) or len(items) > 1000:
        return None

    custom_ids = {
        re.sub(r'[^A-Za-z0-9_-]', '_', str(charge.get('id') or ''))
        for charge in (get_settings().get('billConfig') or {}).get('customCharges', [])
        if isinstance(charge, dict)
    }
    allowed_fields = {
        'totalPoints', 'fixedCost', 'waterCharges', 'reservedFund',
        'fine', 'discount', 'grandTotal',
    }
    allowed_fields.update('customCharge_' + charge_id for charge_id in custom_ids)

    drafts = []
    seen = set()
    users = get_collection('users')
    for item in items:
        if not isinstance(item, dict):
            return None
        user_id = str(item.get('user_id') or item.get('user') or '').strip().upper()
        item_month = str(item.get('billing_month') or item.get('month') or month).strip()
        overrides = item.get('overrides')
        identity = (user_id, item_month)
        if (
            not user_id
            or item_month != month
            or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', item_month)
            or identity in seen
            or not isinstance(overrides, dict)
            or len(overrides) > len(allowed_fields)
        ):
            return None
        seen.add(identity)

        normalized_overrides = {}
        for field, value in overrides.items():
            if field not in allowed_fields:
                return None
            try:
                amount = _money(value)
            except (InvalidOperation, TypeError, ValueError):
                return None
            if amount < 0:
                return None
            normalized_overrides[field] = float(amount)

        account = users.find_one({'id': user_id}, {'role': 1, 'status': 1})
        if (
            not account
            or account.get('role', 'student') != 'student'
            or account.get('status', 'active') != 'active'
        ):
            return None
        drafts.append({
            'user_id': user_id,
            'billing_month': month,
            'overrides': normalized_overrides,
        })
    return drafts


def _json_numbers(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def _authoritative_bill_snapshots(drafts, month, expected_by_user):
    settings = get_settings()
    bill_config = settings.get('billConfig') or {}
    charges = bill_config.get('charges') or {}

    def charge_name(key, fallback):
        charge = charges.get(key) or {}
        return charge.get('name') or fallback

    charge_names = {
        'fixed': charge_name('fixed', 'Fixed Cost'),
        'water': charge_name('water', 'Water Charges'),
        'reserve': charge_name('reserve', 'Reserved Fund'),
        'customCharges': [
            {'id': charge.get('id'), 'name': charge.get('name'), 'mode': charge.get('mode')}
            for charge in bill_config.get('customCharges', [])
            if isinstance(charge, dict)
        ],
    }
    snapshots = []
    for draft in drafts:
        expected = expected_by_user.get(draft['user_id'])
        if not expected:
            raise ValueError('The server could not calculate a bill for the selected student and month.')

        base = expected['base']
        overrides = draft['overrides']
        per_point = _money(expected['perPoint'])
        total_points = _money(overrides.get('totalPoints', base['totalPoints']))
        points_amount = _money(total_points * per_point)
        fixed = _money(overrides.get('fixedCost', base['fixedCost']))
        water = _money(overrides.get('waterCharges', base['waterCharges']))
        reserve = _money(overrides.get('reservedFund', base['reservedFund']))
        fine = _money(overrides.get('fine', base['fine']))
        discount = _money(overrides.get('discount', base['discount']))
        custom_charges = []
        custom_total = Decimal('0.00')
        for charge in base.get('customCharges') or []:
            field = 'customCharge_' + re.sub(r'[^A-Za-z0-9_-]', '_', str(charge.get('id') or ''))
            amount = _money(overrides.get(field, charge['amount']))
            custom_total += amount
            custom_charges.append({**charge, 'amount': float(amount)})
        grand_total = _money(overrides.get(
            'grandTotal',
            points_amount + fixed + water + reserve + custom_total + fine - discount,
        ))
        snapshots.append({
            'user': expected['user'],
            'user_id': expected['user'],
            'name': expected['name'],
            'room': expected['room'],
            'branch': expected['branch'],
            'accountType': expected['accountType'],
            'month': month,
            'billing_month': month,
            'calcVersion': 3,
            'base': _json_numbers(base),
            'overrides': overrides,
            'perPoint': float(per_point),
            'totalPoints': float(total_points),
            'pointsAmount': float(points_amount),
            'fixedCost': float(fixed),
            'waterCharges': float(water),
            'reservedFund': float(reserve),
            'customCharges': custom_charges,
            'individualFine': float(fine),
            'individualDiscount': float(discount),
            'fineReason': expected.get('fineReason') or '',
            'discountReason': expected.get('discountReason') or '',
            'grandTotal': float(grand_total),
            'finalTotal': float(grand_total),
            'amount': float(grand_total),
            'fixedDiscount': float(_money(expected.get('fixedDiscount', 0))),
            'chargeNames': charge_names,
            'entryDays': expected.get('entryDays', 0),
            'missingPoints': expected.get('missing') or [],
            'status': 'pending',
        })
    return snapshots


def _save_snapshots(items, validation_error=None, calculated_bases=None, publication=False):
    def reject(message):
        if validation_error is not None:
            validation_error['message'] = message
        return None

    snapshots = [valid_bill_snapshot(item) for item in items]
    if any(item is None for item in snapshots):
        return reject('A bill has an invalid student ID, billing month, amount, or internally inconsistent calculation.')

    users = get_collection('users')
    identities = []
    for snapshot in snapshots:
        identity = (snapshot['user_id'], snapshot['billing_month'])
        if identity in identities:
            return reject('Duplicate bills for the same student and billing month are not allowed.')
        identities.append(identity)
        account = users.find_one({'id': snapshot['user_id']}, {'role': 1, 'status': 1})
        if (
            not account
            or account.get('role', 'student') != 'student'
            or account.get('status', 'active') != 'active'
        ):
            return reject('A bill references a student who is missing, inactive, or not a student.')

    collection = get_collection('bills')
    calculated = dict(calculated_bases or {})

    # Validate every point-based snapshot against the authoritative records
    # before writing any bill. A stale snapshot in a mixed-month request must
    # not leave earlier items from that request partially persisted.
    for snapshot in snapshots:
        if int(snapshot.get('calcVersion') or 0) < 3:
            continue
        month = snapshot['billing_month']
        if month not in calculated:
            calculated[month] = _calculate_server_bases(month)
        expected = calculated[month].get(snapshot['user_id'])
        if not expected:
            return reject('The server could not calculate a bill for the selected student and month.')
        mismatches = snapshot_calculation_mismatches(snapshot, expected)
        if mismatches:
            component_list = ', '.join(mismatches)
            current_app.logger.warning(
                'Bill calculation validation failed for month %s; mismatched components: %s',
                month,
                component_list,
            )
            return reject(
                'A bill calculation does not match server data. Mismatched components: '
                + component_list
                + '. Refresh the selected month and review any manual overrides.'
            )

    saved = []
    for snapshot in snapshots:
        identity = {
            'user_id': snapshot['user_id'],
            'billing_month': snapshot['billing_month'],
        }
        existing = collection.find_one(identity, {'status': 1, 'paid_at': 1, 'paidAt': 1, 'created_at': 1})
        existing_full = collection.find_one(identity) if existing else None
        unchanged = bool(
            existing_full
            and int(existing_full.get('revision') or 1) == int(snapshot.get('revision') or 1)
            and existing_full.get('base') == snapshot.get('base')
            and existing_full.get('overrides', {}) == snapshot.get('overrides', {})
            and existing_full.get('perPoint') == snapshot.get('perPoint')
            and existing_full.get('grandTotal', existing_full.get('final_total')) == snapshot.get('grandTotal', snapshot.get('final_total'))
        )
        if unchanged:
            saved.append(serialize_bill(existing_full))
            continue
        if existing and existing.get('status') == 'paid':
            snapshot['status'] = 'paid'
            paid_at = existing.get('paid_at') or existing.get('paidAt')
            snapshot['paid_at'] = paid_at
            snapshot['paidAt'] = paid_at
        else:
            snapshot.setdefault('status', existing.get('status', 'pending') if existing else 'pending')
        if publication:
            now = datetime.now(timezone.utc)
            snapshot['revision'] = int(existing_full.get('revision') or 1) + 1 if existing_full else 1
            snapshot['generationStatus'] = 'Updated' if existing_full else 'Generated'
            snapshot['generatedAt'] = (
                existing_full.get('generatedAt')
                or existing_full.get('generated_at')
                or existing_full.get('created_at')
                or now
            ) if existing_full else now
        collection.update_one(
            identity,
            {
                '$set': snapshot,
                '$setOnInsert': {'created_at': datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        saved_bill = collection.find_one(identity)
        if saved_bill:
            saved.append(serialize_bill(saved_bill))
    has_cancellations = False
    for month in sorted({snapshot['billing_month'] for snapshot in snapshots}):
        cancellations = list(get_collection('meal_cancellations').find({
            'date': {'$regex': '^' + re.escape(month) + '-'},
            'status': 'cancelled',
        }))
        for cancellation in cancellations:
            has_cancellations = True
            apply_meal_cancellation_to_bills(
                month,
                str(cancellation.get('_id') or ''),
                cancellation,
            )
    if has_cancellations:
        refreshed = []
        for snapshot in snapshots:
            bill = collection.find_one({
                'user_id': snapshot['user_id'],
                'billing_month': snapshot['billing_month'],
            })
            if bill:
                refreshed.append(serialize_bill(bill))
        saved = refreshed
    return saved


def _recalculate_existing_snapshots(month, user_ids, validation_error):
    collection = get_collection('bills')
    existing_by_user = {}
    for user_id in user_ids:
        identity = {'user_id': user_id, 'billing_month': month}
        existing = collection.find_one(identity)
        if not existing or int(existing.get('calcVersion') or 0) < 3:
            validation_error['message'] = 'Every recalculation must reference an existing point-based bill for the selected month.'
            return None
        existing_by_user[user_id] = existing

    items = [
        {
            'user_id': user_id,
            'month': month,
            'overrides': existing_by_user[user_id].get('overrides') or {},
        }
        for user_id in user_ids
    ]
    drafts = _validated_bill_drafts(items, month)
    if drafts is None:
        validation_error['message'] = 'An existing bill references an inactive student or has invalid manual overrides.'
        return None

    expected_by_user = _calculate_server_bases(month)
    snapshots = _authoritative_bill_snapshots(drafts, month, expected_by_user)
    calculated_fields = (
        'base', 'overrides', 'perPoint', 'totalPoints', 'pointsAmount',
        'fixedCost', 'waterCharges', 'reservedFund', 'customCharges',
        'individualFine', 'individualDiscount', 'grandTotal',
    )
    for snapshot in snapshots:
        existing = existing_by_user[snapshot['user_id']]
        changed = any(existing.get(field) != snapshot.get(field) for field in calculated_fields)
        snapshot['status'] = existing.get('status') or 'pending'
        snapshot['revision'] = int(existing.get('revision') or 1) + (1 if changed else 0)
        if existing.get('paid_at') is not None:
            snapshot['paid_at'] = existing['paid_at']
        if existing.get('paidAt') is not None:
            snapshot['paidAt'] = existing['paidAt']
        for field in ('generatedAt', 'created_at'):
            if existing.get(field) is not None:
                snapshot[field] = existing[field]
        if changed:
            snapshot['generationStatus'] = 'Updated'
            snapshot['updatedAt'] = datetime.now(timezone.utc)
    return _save_snapshots(
        snapshots,
        validation_error,
        calculated_bases={month: expected_by_user},
    )


def _calculate_server_bases(month):

    settings = get_settings()
    users = list(get_collection('users').find())
    approved_no_food = get_approved_no_food_map(month=month)
    entries = [
        apply_approved_no_food(entry, approved_no_food)
        for entry in get_collection('mess_entries').find()
    ]
    records = list(get_collection('meal_records').find())
    weekly_menu = list(get_collection('weekly_menu').find())
    cancellations = list(get_collection('meal_cancellations').find({
        'date': {'$regex': '^' + re.escape(month) + '-'},
        'status': 'cancelled',
    }))
    today = mess_now().date().isoformat()
    today_menu = get_collection('today_menu').find_one({'date': today}) or {}
    return calculate_bill_bases(
        month,
        settings,
        users,
        entries,
        records,
        weekly_menu,
        today_menu,
        cancellations=cancellations,
    )


def _calculate_server_summary(month):

    settings = get_settings()
    users = list(get_collection('users').find())
    approved_no_food = get_approved_no_food_map(month=month)
    entries = [
        apply_approved_no_food(entry, approved_no_food)
        for entry in get_collection('mess_entries').find()
    ]
    records = list(get_collection('meal_records').find())
    weekly_menu = list(get_collection('weekly_menu').find())
    cancellations = list(get_collection('meal_cancellations').find({
        'date': {'$regex': '^' + re.escape(month) + '-'},
        'status': 'cancelled',
    }))
    today = mess_now().date().isoformat()
    today_menu = get_collection('today_menu').find_one({'date': today}) or {}
    return calculate_bill_summary(
        month,
        settings,
        users,
        entries,
        records,
        weekly_menu,
        today_menu,
        cancellations=cancellations,
    )


def apply_meal_cancellation_to_bills(month, cancellation_id, cancellation):
    def mongo_numbers(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {key: mongo_numbers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [mongo_numbers(item) for item in value]
        return value

    expected_by_user = _calculate_server_bases(month)
    bills = get_collection('bills')
    adjustments = get_collection('meal_cancellation_adjustments')
    for bill in bills.find({'billing_month': month}):
        user_id = str(bill.get('user_id') or bill.get('user') or '').upper()
        expected = expected_by_user.get(user_id)
        if not expected:
            continue
        old_total = bill.get('grandTotal', bill.get('final_total', bill.get('finalTotal', 0)))
        base = expected.get('base') or {}
        overrides = bill.get('overrides') or {}
        if not isinstance(overrides, dict):
            overrides = {}

        def resolved(field, fallback):
            return _money(overrides[field]) if field in overrides else _money(fallback)

        total_points = resolved('totalPoints', base.get('totalPoints', 0))
        per_point = _money(expected.get('perPoint', bill.get('perPoint', 0)))
        points_amount = resolved('pointsAmount', total_points * per_point)
        fixed = resolved('fixedCost', base.get('fixedCost', 0))
        water = resolved('waterCharges', base.get('waterCharges', 0))
        reserve = resolved('reservedFund', base.get('reservedFund', 0))
        fine = resolved('fine', base.get('fine', 0))
        discount = resolved('discount', base.get('discount', 0))
        custom_charges = []
        custom_total = Decimal('0.00')
        for charge in base.get('customCharges') or []:
            field = 'customCharge_' + re.sub(r'[^a-zA-Z0-9_-]', '_', str(charge.get('id') or ''))
            amount = resolved(field, charge.get('amount', 0))
            custom_charges.append({**charge, 'amount': float(amount)})
            custom_total += amount
        grand_total = resolved(
            'grandTotal',
            points_amount + fixed + water + reserve + custom_total + fine - discount,
        )
        now = datetime.now(timezone.utc)
        bills.update_one(
            {'_id': bill['_id']},
            {'$set': {
                'base': mongo_numbers(base),
                'totalPoints': float(total_points),
                'perPoint': float(per_point),
                'pointsAmount': float(points_amount),
                'fixedCost': float(fixed),
                'waterCharges': float(water),
                'reservedFund': float(reserve),
                'individualFine': float(fine),
                'individualDiscount': float(discount),
                'customCharges': custom_charges,
                'grandTotal': float(grand_total),
                'finalTotal': float(grand_total),
                'final_total': float(grand_total),
                'updated_at': now,
            }},
        )
        adjustment_key = f'{cancellation_id}-{user_id}'
        adjustments.update_one(
            {'dedupeKey': adjustment_key},
            {'$setOnInsert': {
                'dedupeKey': adjustment_key,
                'cancellation_id': str(cancellation_id),
                'billing_month': month,
                'date': cancellation.get('date'),
                'meal_type': cancellation.get('meal_type'),
                'user_id': user_id,
                'previous_total': old_total,
                'adjusted_total': float(grand_total),
                'adjusted_by': cancellation.get('cancelled_by'),
                'adjusted_at': now,
            }},
            upsert=True,
        )


def serialize_bill(bill):
    result = dict(bill)
    if '_id' in result:
        result['_id'] = str(result['_id'])
    result['user_id'] = result.get('user_id') or result.get('user')
    result['user'] = result['user_id']
    result['billing_month'] = result.get('billing_month') or result.get('billingMonth') or result.get('month')
    result['month'] = result['billing_month']
    result['billingMonth'] = result['billing_month']
    final_total = next(
        (result[field] for field in ('grandTotal', 'finalTotal', 'final_total', 'amount')
         if result.get(field) is not None),
        0,
    )
    result['grandTotal'] = final_total
    result['finalTotal'] = final_total
    result['final_total'] = final_total
    result['amount'] = final_total
    result['totalPoints'] = result.get('totalPoints', result.get('total_points'))
    result['pointsAmount'] = result.get('pointsAmount', result.get('mess_charges'))
    result['perPoint'] = result.get('perPoint', result.get('per_point_rate'))
    result['fixedCost'] = result.get('fixedCost', result.get('fixed_cost'))
    result['waterCharges'] = result.get('waterCharges', result.get('water_charges'))
    result['reservedFund'] = result.get('reservedFund', result.get('reserved_fund'))
    result['individualFine'] = result.get('individualFine', result.get('fine', 0))
    result['individualDiscount'] = result.get('individualDiscount', result.get('discount', 0))
    result['paidAt'] = result.get('paidAt', result.get('paid_at'))
    result['generatedAt'] = result.get('generatedAt', result.get('generated_at', result.get('created_at')))
    result['updatedAt'] = result.get('updatedAt', result.get('updated_at'))
    for key in ('paidAt', 'generatedAt', 'updatedAt'):
        if isinstance(result.get(key), datetime):
            result[key] = result[key].isoformat()
    return result


@bills_bp.route('/', methods=['GET'])
@login_required
def get_bills():
    month = request.args.get('month')
    if month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400

    query = {}
    if current_user.role != 'admin':
        query['user_id'] = current_user.id
    if month:
        query['billing_month'] = month

    bills = list(get_collection('bills').find(query).sort('billing_month', -1))
    return jsonify({'bills': [serialize_bill(bill) for bill in bills]})


@bills_bp.route('/drafts', methods=['GET'])
@login_required
def get_bill_drafts():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403
    month = request.args.get('month', '')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400
    try:
        drafts = list(get_collection('bill_drafts').find(
            {'billing_month': month},
            {'_id': 0, 'user_id': 1, 'billing_month': 1, 'overrides': 1, 'updated_at': 1},
        ))
        for draft in drafts:
            if isinstance(draft.get('updated_at'), datetime):
                draft['updated_at'] = draft['updated_at'].isoformat()
    except PyMongoError:
        return jsonify({'success': False, 'message': 'Saved bill drafts could not be loaded from the database.'}), 503
    return jsonify({'success': True, 'month': month, 'drafts': drafts})


@bills_bp.route('/drafts', methods=['PUT'])
@login_required
def save_bill_drafts():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    month = data.get('month')
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400
    if not isinstance(data.get('drafts'), list):
        return jsonify({'success': False, 'message': 'A drafts array is required'}), 400

    try:
        drafts = _validated_bill_drafts(data['drafts'], month)
        if drafts is None:
            return jsonify({'success': False, 'message': 'Every draft must contain an active student, the selected month, and valid editable values.'}), 400
        collection = get_collection('bill_drafts')
        now = datetime.now(timezone.utc)
        for draft in drafts:
            collection.update_one(
                {
                    'user_id': draft['user_id'],
                    'billing_month': month,
                },
                {
                    '$set': {
                        'overrides': draft['overrides'],
                        'updated_at': now,
                    },
                    '$setOnInsert': {'created_at': now},
                },
                upsert=True,
            )
        user_ids = [draft['user_id'] for draft in drafts]
        collection.delete_many({
            'billing_month': month,
            'user_id': {'$nin': user_ids},
        })
        saved = list(collection.find(
            {'billing_month': month},
            {'_id': 0, 'user_id': 1, 'billing_month': 1, 'overrides': 1, 'updated_at': 1},
        ))
        for draft in saved:
            if isinstance(draft.get('updated_at'), datetime):
                draft['updated_at'] = draft['updated_at'].isoformat()
    except PyMongoError:
        return jsonify({'success': False, 'message': 'Bill edits could not be saved to the database.'}), 503
    return jsonify({'success': True, 'month': month, 'saved': len(saved), 'drafts': saved})


@bills_bp.route('/point-rate', methods=['GET'])
@login_required
def get_point_rate():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403
    month = request.args.get('month', '')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400
    try:
        summary = _calculate_server_summary(month)
    except (InvalidOperation, TypeError, ValueError, RuntimeError, PyMongoError):
        return jsonify({
            'success': False,
            'message': 'The server could not calculate the point rate from current billing data.',
        }), 503
    return jsonify({
        'success': True,
        'month': month,
        'totalUserPoints': float(summary['totalUserPoints']),
        'totalExpenses': float(summary['totalExpenses']),
        'perPoint': float(summary['perPoint']) if summary['perPoint'] is not None else None,
        'hasPoints': summary['totalUserPoints'] > 0,
        'activeUsers': summary['activeUsers'],
        'missingFoodPoints': summary['missingFoodPoints'],
    })


@bills_bp.route('/snapshots', methods=['PUT'])
@login_required
def save_bill_snapshots():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    month = data.get('month')
    if 'recalculate' in data:
        if (
            set(data) != {'month', 'recalculate', 'user_ids'}
            or data.get('recalculate') is not True
            or not isinstance(month, str)
            or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month)
            or not isinstance(data.get('user_ids'), list)
            or not data['user_ids']
            or len(data['user_ids']) > 1000
        ):
            return jsonify({
                'success': False,
                'message': 'A valid month and list of existing bill identities are required for recalculation.',
            }), 400
        user_ids = []
        for value in data['user_ids']:
            if not isinstance(value, str) or not value.strip():
                return jsonify({'success': False, 'message': 'Every bill identity must contain a student ID.'}), 400
            user_id = value.strip().upper()
            if user_id in user_ids:
                return jsonify({'success': False, 'message': 'Duplicate bills for the same student and billing month are not allowed.'}), 400
            user_ids.append(user_id)
        validation_error = {}
        try:
            saved = _recalculate_existing_snapshots(month, user_ids, validation_error)
        except (InvalidOperation, TypeError, ValueError, RuntimeError, PyMongoError):
            current_app.logger.exception('Authoritative bill snapshot recalculation failed for month %s.', month)
            return jsonify({
                'success': False,
                'message': 'Existing bills could not be recalculated from authoritative server data.',
            }), 503
        if saved is None:
            return jsonify({
                'success': False,
                'message': validation_error.get('message', 'Existing bills could not be recalculated.'),
            }), 400
        return jsonify({'success': True, 'month': month, 'saved': len(saved), 'bills': saved})

    if not isinstance(data.get('bills'), list):
        return jsonify({'success': False, 'message': 'A bills array is required'}), 400
    if len(data['bills']) > 1000:
        return jsonify({'success': False, 'message': 'Too many bill snapshots'}), 400

    validation_error = {}
    saved = _save_snapshots(data['bills'], validation_error)
    if saved is None:
        return jsonify({
            'success': False,
            'message': validation_error.get(
                'message',
                'Every bill must have a valid student, month, amount, and internally consistent calculation',
            ),
        }), 400
    return jsonify({'success': True, 'saved': len(saved), 'bills': saved})

@bills_bp.route('/generate', methods=['POST'])
@login_required
def generate_bills():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required'}), 400
    month = data.get('month')
    items = data.get('bills')
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        return jsonify({'success': False, 'message': 'Month must use YYYY-MM format'}), 400
    if not isinstance(items, list) or not items or len(items) > 1000:
        return jsonify({'success': False, 'message': 'A non-empty bills array of at most 1000 bills is required'}), 400
    if any(not isinstance(item, dict) or str(item.get('month') or item.get('billing_month') or '') != month for item in items):
        return jsonify({'success': False, 'message': 'Every bill must match the selected billing month'}), 400
    expected_fields = {'user_id', 'month', 'overrides'}
    if any(set(item) != expected_fields for item in items):
        return jsonify({
            'success': False,
            'message': 'Bill generation accepts only student IDs, the billing month, and explicit manual overrides; amounts are calculated by the server.',
        }), 400

    if len({str(item['user_id']).strip().upper() for item in items}) != len(items):
        return jsonify({'success': False, 'message': 'Duplicate bills for the same student and billing month are not allowed.'}), 400

    validation_error = {}
    try:
        drafts = _validated_bill_drafts(items, month)
        if drafts is None:
            return jsonify({
                'success': False,
                'message': 'Every bill must reference an active student and contain valid manual overrides for the selected month.',
            }), 400
        expected_by_user = _calculate_server_bases(month)
        snapshots = _authoritative_bill_snapshots(drafts, month, expected_by_user)
        saved = _save_snapshots(
            snapshots,
            validation_error,
            calculated_bases={month: expected_by_user},
            publication=True,
        )
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    except (InvalidOperation, TypeError, RuntimeError, PyMongoError):
        current_app.logger.exception('Authoritative bill generation failed for month %s.', month)
        return jsonify({
            'success': False,
            'message': 'Bills could not be calculated or saved from authoritative server data.',
        }), 503
    if saved is None:
        return jsonify({
            'success': False,
            'message': validation_error.get(
                'message',
                'Every bill must have a valid student, month, amount, and internally consistent calculation',
            ),
        }), 400
    try:
        get_collection('bill_drafts').delete_many({'billing_month': month})
    except PyMongoError:
        return jsonify({
            'success': False,
            'message': 'Bills were published, but the saved drafts could not be cleared. Retry Generate to finish cleanup.',
        }), 503
    return jsonify({'success': True, 'saved': len(saved), 'bills': saved})

@bills_bp.route('/update', methods=['POST'])
@login_required
def update_bills():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    return jsonify({
        'success': False,
        'message': 'Legacy bill recalculation is disabled. Recalculate bills in the admin bill screen and save the point-based snapshots.',
    }), 409

@bills_bp.route('/<bill_id>/mark-paid', methods=['POST'])
@login_required
def mark_bill_paid(bill_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    get_collection('bills').update_one(
        {'_id': ObjectId(bill_id)},
        {'$set': {
            'status': 'paid',
            'paid_at': datetime.utcnow()
        }}
    )
    return jsonify({'success': True})

@bills_bp.route('/expenses', methods=['GET'])
@login_required
def get_expenses():
    month = request.args.get('month')
    query = {}
    if month:
        query['billing_month'] = month
    expenses = list(get_collection('expenses').find(query))
    result = []
    for exp in expenses:
        exp_dict = dict(exp)
        if '_id' in exp_dict:
            exp_dict['_id'] = str(exp_dict['_id'])
        result.append(exp_dict)
    return jsonify({'expenses': result})

@bills_bp.route('/expenses', methods=['POST'])
@login_required
def add_expense():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json()
    expense_data = {
        'name': data.get('name'),
        'amount': data.get('amount'),
        'billing_month': data.get('billing_month'),
        'created_at': datetime.utcnow()
    }
    get_collection('expenses').insert_one(expense_data)
    return jsonify({'success': True, 'expense': expense_data})

@bills_bp.route('/charge-configs', methods=['GET'])
@login_required
def get_charge_configs():
    month = request.args.get('month')
    query = {}
    if month:
        query['billing_month'] = month
    configs = list(get_collection('charge_configs').find(query))
    result = []
    for config in configs:
        config_dict = dict(config)
        if '_id' in config_dict:
            config_dict['_id'] = str(config_dict['_id'])
        result.append(config_dict)
    return jsonify({'configs': result})

@bills_bp.route('/charge-configs', methods=['POST'])
@login_required
def save_charge_config():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json()
    config_data = {
        'config_type': data.get('type'),
        'name': data.get('name'),
        'amount': data.get('amount', 0),
        'charge_mode': data.get('mode', 'split'),
        'billing_month': data.get('billing_month'),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    get_collection('charge_configs').insert_one(config_data)
    return jsonify({'success': True})

@bills_bp.route('/user-adjustments', methods=['POST'])
@login_required
def save_user_adjustment():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json()
    adj_data = {
        'user_id': data.get('user_id'),
        'billing_month': data.get('billing_month'),
        'fine': data.get('fine', 0),
        'fine_reason': data.get('fine_reason'),
        'discount': data.get('discount', 0),
        'discount_reason': data.get('discount_reason'),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    get_collection('user_adjustments').insert_one(adj_data)
    return jsonify({'success': True})

@bills_bp.route('/archive', methods=['GET'])
@login_required
def get_bill_archive():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    archive = list(get_collection('bill_archive').find().sort('archived_at', -1))
    result = []
    for a in archive:
        a_dict = dict(a)
        if '_id' in a_dict:
            a_dict['_id'] = str(a_dict['_id'])
        result.append(a_dict)
    return jsonify({'archive': result})


@bills_bp.route('/archive', methods=['POST'])
@login_required
def save_bill_archive():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Admin role required for this billing operation'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('archive'), list):
        return jsonify({'success': False, 'message': 'An archive array is required'}), 400
    if len(data['archive']) > 5000:
        return jsonify({'success': False, 'message': 'Too many archived bills'}), 400

    documents = []
    for item in data['archive']:
        if not isinstance(item, dict):
            return jsonify({'success': False, 'message': 'Invalid archived bill'}), 400
        user_id = str(item.get('user_id') or item.get('user') or '').strip().upper()
        month = str(item.get('billing_month') or item.get('billingMonth') or item.get('month') or '').strip()
        archived_at = str(item.get('archived_at') or item.get('archivedAt') or '').strip()
        if (
            not user_id
            or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month)
            or not archived_at
        ):
            return jsonify({'success': False, 'message': 'Archived bills need a student ID, valid billing month, and archive time'}), 400
        document = {
            key: value for key, value in item.items()
            if key not in {'_id', 'password', 'password_hash', 'user_id', 'billing_month'}
        }
        document.update({
            'user_id': user_id,
            'billing_month': month,
            'archived_at': archived_at,
        })
        document['archive_key'] = '|'.join((
            user_id,
            month,
            str(item.get('revision') or ''),
            archived_at,
        ))
        documents.append(document)

    collection = get_collection('bill_archive')
    for document in documents:
        archive_key = document.pop('archive_key')
        collection.update_one(
            {'archive_key': archive_key},
            {'$setOnInsert': {**document, 'archive_key': archive_key}},
            upsert=True,
        )
    return jsonify({'success': True, 'saved': len(documents)})

# --- meal_records.py ---
import re
from datetime import date, time, timedelta, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from pymongo.errors import PyMongoError
from pymongo import ReturnDocument


meal_records_bp = Blueprint("meal_records", __name__)
MEAL_FIELDS = {"b": "breakfast", "l": "lunch", "d": "dinner"}
MEAL_TIMES = {
    "b": ("breakfastOpen", "breakfastClose"),
    "l": ("lunchOpen", "lunchClose"),
    "d": ("dinnerOpen", "dinnerClose"),
}
APPROVER_ROLES = {"admin", "secretary", "mess_secretary"}
NO_FOOD_MEALS = {"b": "breakfast", "l": "lunch", "d": "dinner"}
NO_FOOD_REVIEW_LEASE = timedelta(minutes=2)


def _serialize_no_food_request(request):
    result = dict(request)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    result.pop("review_token", None)
    for field in ("requested_at", "reviewed_at", "created_at", "updated_at"):
        value = result.get(field)
        if hasattr(value, "isoformat"):
            result[field] = value.isoformat()
    result["request_id"] = result.get("request_id") or result.get("_id")
    result["meal"] = result.get("meal") or result.get("meal_type")
    result["status"] = result.get("status") or "pending"
    return result


def _meal_from_request(value):
    meal = str(value or "").strip().lower()
    aliases = {"breakfast": "b", "lunch": "l", "dinner": "d"}
    return aliases.get(meal, meal)


def _no_food_menu_name(date_value, short, settings):
    return _menu_for(date_value, settings).get(short) or ""


def _no_food_notification(request_data, status):
    request_id = str(request_data.get("_id") or request_data.get("request_id") or "")
    user_id = str(request_data.get("user_id") or "")
    label = NO_FOOD_MEALS.get(request_data.get("meal"), request_data.get("meal"))
    message = (
        f"Your no-food request for {label} on {request_data.get('date')} was "
        f"{status}."
    )
    get_collection("notifications").update_one(
        {"dedupeKey": f"no-food-status-{request_id}-{status}"},
        {
            "$setOnInsert": {
                "title": f"No-food request {status}",
                "message": message,
                "date": request_data.get("date"),
                "target": "home",
                "audience": "user",
                "user_id": user_id,
                "dedupeKey": f"no-food-status-{request_id}-{status}",
                "created_at": utc_now(),
            }
        },
        upsert=True,
    )




def _serialize(record):
    result = dict(record)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


def _entry_for(user_id, date_value):
    return get_collection("mess_entries").find_one(
        {"user_id": user_id, "date": date_value}
    ) or {}


def _menu_for(date_value, settings):
    snapshots = settings.get("menuSnapshots") or {}
    snapshot = snapshots.get(date_value)
    if isinstance(snapshot, dict):
        return {short: snapshot.get(short) or "" for short in MEAL_FIELDS}
    from datetime import date

    target = date.fromisoformat(date_value)
    day_name = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[target.weekday()]
    menu = next(
        (
            row for row in get_weekly_menu()
            if str(row.get("day") or "").strip().lower() == day_name.lower()
        ),
        {},
    )
    return {short: menu.get(short) or "" for short in MEAL_FIELDS}


def _meal_point(food_name, settings):
    points = settings.get("foodPoints") or {}
    key = re.sub(r"\s+", " ", str(food_name or "").strip()).lower()
    food = points.get(key)
    if not isinstance(food, dict):
        return 0
    try:
        value = float(food.get("point", 0))
    except (TypeError, ValueError):
        return 0
    return value if value >= 0 else 0


def _recalculate_meal(
    meal, expected, short, date_value, settings, *, admin_approved=False
):
    no_food = meal.get("noFood")
    if isinstance(no_food, dict) and no_food.get("status") == "approved":
        # Keep this branch ahead of cutoff hydration and the normal meal
        # calculator. It is the persisted, auditable zero-point state.
        meal["expectedQuantity"] = expected
        meal["actualQuantity"] = 0
        meal["approvedQuantity"] = 0
        meal["calculation"] = {
            "expected_quantity": expected,
            "actual_quantity": 0,
            "scheduled_quantity": expected,
            "entered_quantity": 0,
            "billable_quantity": 0,
            "approved_quantity": 0,
            "normal_meal_points": 0.0,
            "unauthorized_quantity": 0,
            "unauthorized_meal_points": 0.0,
            "permission_fee": 0.0,
            "unauthorized_fine_points": 0.0,
            "missing_fine_points": 0.0,
            "additional_fine": 0.0,
            "final_billable_points": 0.0,
            "cancelled": False,
            "permission_status": "not_required",
            "no_food": True,
        }
        return meal
    cancelled = is_meal_cancelled(date_value, short)
    if (
        not cancelled
        and isinstance(no_food, dict)
        and no_food.get("status") == "rejected"
        and int(meal.get("q", 0) or 0) <= 0
    ):
        # A rejected no-food request is not an approval for zero points, but
        # it must not trigger the punitive double-missing-meal fine. Charge
        # the ordinary fixed expected meal points for this meal only.
        point_value = _meal_point(_menu_for(date_value, settings)[short], settings)
        fixed_points = (Decimal(str(point_value)) * Decimal(str(expected))).quantize(Decimal("0.01"))
        meal["expectedQuantity"] = expected
        meal["actualQuantity"] = 0
        meal["approvedQuantity"] = 0
        meal["calculation"] = {
            "expected_quantity": expected,
            "actual_quantity": 0,
            "scheduled_quantity": expected,
            "entered_quantity": 0,
            "billable_quantity": expected,
            "approved_quantity": 0,
            "normal_meal_points": float(fixed_points),
            "unauthorized_quantity": 0,
            "unauthorized_meal_points": 0.0,
            "permission_fee": 0.0,
            "unauthorized_fine_points": 0.0,
            "missing_fine_points": 0.0,
            "additional_fine": 0.0,
            "final_billable_points": float(fixed_points),
            "cancelled": False,
            "permission_status": "not_required",
            "no_food": False,
            "fine_reason": "No-food request rejected; ordinary fixed meal points only.",
        }
        return meal
    permission = meal.get("permission")
    if not isinstance(permission, dict):
        permission = {"status": "not_requested", "approved_quantity": 0}
    approved_quantity = (
        permission.get("approved_quantity", 0)
        if permission.get("status") == "approved"
        else 0
    )

    close_time = _valid_menu_time(
        settings,
        {"b": "breakfastClose", "l": "lunchClose", "d": "dinnerClose"}[short],
    )
    from datetime import date

    target_date = date.fromisoformat(date_value)
    now = mess_now()
    after_cutoff = target_date < now.date() or (
        target_date == now.date() and now.time() >= close_time
    )
    calculation_actual = (
        expected
        if (meal.get("optOut") or admin_approved) and not cancelled
        else meal.get("q")
    )
    result = calculate_meal_points(
        expected,
        calculation_actual,
        approved_quantity,
        _meal_point(_menu_for(date_value, settings)[short], settings),
        after_cutoff=after_cutoff,
        cancelled=cancelled,
        permission_pending=permission.get("status") == "pending",
    )
    result["cancelled"] = cancelled
    result["permission_status"] = permission.get("status", "not_requested")
    if result["unauthorized_quantity"]:
        status = permission.get("status")
        reason = {
            "pending": "permission pending, not approved",
            "rejected": "permission rejected",
            "not_requested": "permission not requested",
        }.get(status, "no approved permission")
        result["fine_reason"] = (
            "Unauthorized extra portions charged at double points; " + reason
        )
    if meal.get("optOut") and not cancelled:
        try:
            opt_out_fine = Decimal(str(meal.get("finePoints", 0) or 0))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Opt-out fine points must be numeric.")
        if not opt_out_fine.is_finite() or opt_out_fine < 0:
            raise ValueError("Opt-out fine points must be finite and non-negative.")
        result["additional_fine"] = opt_out_fine
        result["final_billable_points"] = (
            Decimal(str(result["final_billable_points"])) + opt_out_fine
        )
    if (admin_approved or meal.get("optOut")) and not cancelled:
        result["actual_quantity"] = meal.get("q", 0)
        result["entered_quantity"] = meal.get("q", 0)
    for key, value in tuple(result.items()):
        if hasattr(value, "as_tuple"):
            result[key] = float(value)
    meal["expectedQuantity"] = result["expected_quantity"]
    meal["actualQuantity"] = result["actual_quantity"]
    meal["approvedQuantity"] = result["approved_quantity"]
    meal["calculation"] = result
    return meal


def recalculate_existing_meal_record(user_id, date_value, entry=None, record=None):
    collection = get_collection("meal_records")
    record = record or collection.find_one({
            "user_id": user_id,
            "date": date_value,
            "writeVersion": 2,
        }) or collection.find_one({"user_id": user_id, "date": date_value})
    if not isinstance(record, dict):
        return
    if not isinstance(entry, dict):
        entry = _entry_for(user_id, date_value)
    settings = get_settings()
    meals = record.get("meals") or {}
    if not isinstance(meals, dict):
        return
    for short, meal in meals.items():
        if short in MEAL_FIELDS and isinstance(meal, dict):
            expected = int(entry.get(MEAL_FIELDS[short], entry.get(short, 0)) or 0)
            meals[short] = _recalculate_meal(
                meal,
                expected,
                short,
                date_value,
                settings,
                admin_approved=bool(entry.get("adminApproved")),
            )
    result = collection.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "meals": meals,
            "updated_at": mess_now().isoformat(),
            "writeVersion": 2,
        }},
    )
    if not _write_was_applied(result):
        raise RuntimeError("The recalculated meal record was not persisted.")


def _record_with_current_calculations(record, settings):
    result = dict(record)
    date_value = str(result.get("date") or "")
    entry = _entry_for(result.get("user_id"), date_value)
    if not isinstance(entry, dict):
        entry = {}
    meals = dict(result.get("meals") or {})
    for short, meal in meals.items():
        if short in MEAL_FIELDS and isinstance(meal, dict):
            no_food = meal.get("noFood")
            if isinstance(no_food, dict) and no_food.get("review_state"):
                selector = {
                    "user_id": result.get("user_id"),
                    "date": date_value,
                    "meal": short,
                }
                request_id = no_food.get("request_id")
                if ObjectId.is_valid(str(request_id or "")):
                    selector["_id"] = ObjectId(str(request_id))
                request_data = get_collection("no_food_requests").find_one(selector)
                meal = dict(meal)
                marker = dict(no_food)
                marker["status"] = (request_data or {}).get("status", "pending")
                marker.pop("review_state", None)
                meal["noFood"] = marker
            expected = int(entry.get(MEAL_FIELDS[short], entry.get(short, 0)) or 0)
            meals[short] = _recalculate_meal(
                dict(meal),
                expected,
                short,
                date_value,
                settings,
                admin_approved=bool(entry.get("adminApproved")),
            )
    result["meals"] = meals
    return _serialize(result)


def _is_open(short, settings):
    open_key, close_key = MEAL_TIMES[short]
    opened = time.fromisoformat(settings.get(open_key, "00:00"))
    closed = time.fromisoformat(settings.get(close_key, "23:59"))
    now = mess_now().time().replace(tzinfo=None)
    return opened <= now < closed


def _validate_meal(short, meal):
    if meal is None:
        return None
    if not isinstance(meal, dict):
        return "Each saved meal must be an object or null."
    quantity = meal.get("q")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 99:
        return "Meal quantities must be whole numbers from 0 to 99."
    if "t" in meal and (
        not isinstance(meal["t"], str)
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", meal["t"])
    ):
        return "Meal time must use HH:MM format."
    if set(meal) - {"q", "t", "permissionChoice", "optOut"}:
        return "Meal records contain unsupported fields."
    if "optOut" in meal and not isinstance(meal["optOut"], bool):
        return "optOut must be a boolean."
    choice = meal.get("permissionChoice")
    if choice is not None and (
        not isinstance(choice, str)
        or choice not in {"with_permission", "without_permission"}
    ):
        return "permissionChoice must be with_permission or without_permission."
    return None


def _save_meals(
    user_id,
    room,
    date_value,
    incoming_meals,
    *,
    admin=False,
    record=None,
    confirmed=None,
    confirmed_at=None,
):
    collection = get_collection("meal_records")
    entry = _entry_for(user_id, date_value)
    settings = get_settings()
    existing = record or collection.find_one({
        "user_id": user_id,
        "date": date_value,
        "writeVersion": 2,
    }) or collection.find_one({
        "user_id": user_id,
        "date": date_value,
    }) or {}
    meals = dict(existing.get("meals") or {})

    for short, incoming in incoming_meals.items():
        if short not in MEAL_FIELDS:
            return None, ({"success": False, "message": "Unknown meal key."}, 400)
        error = _validate_meal(short, incoming)
        if error:
            return None, ({"success": False, "message": error}, 400)
        if is_meal_cancelled(date_value, short):
            return None, ({
                "success": False,
                "message": f"{MEAL_FIELDS[short].capitalize()} is cancelled for this date.",
            }, 409)
        if incoming is None:
            continue

        expected = int(entry.get(MEAL_FIELDS[short], entry.get(short, 0)) or 0)
        previous = meals.get(short) or {}
        try:
            no_food_request = get_collection("no_food_requests").find_one(
                {
                    "user_id": user_id,
                    "date": date_value,
                    "meal": short,
                    "status": {"$in": ["pending", "approved"]},
                }
            )
        except (KeyError, RuntimeError):
            no_food_request = None
        if no_food_request or (
            isinstance(previous.get("noFood"), dict)
            and previous["noFood"].get("status") == "approved"
        ):
            return None, ({
                "success": False,
                "message": "A no-food request is pending or approved for this meal; a normal meal entry is not allowed.",
            }, 409)
        changed = incoming.get("q") != previous.get("q")
        choice = incoming.get("permissionChoice")
        if incoming.get("q", 0) > expected and choice is None:
            permission = previous.get("permission") or {}
            if not permission.get("status") in {"pending", "approved", "rejected"}:
                return None, ({
                    "success": False,
                    "message": "Choose With Permission or Without Permission for extra portions.",
                }, 400)
        if not admin and changed and not _is_open(short, settings):
            return None, ({
                "success": False,
                "message": "This meal is outside its configured entry window.",
            }, 403)

        meal = dict(previous)
        meal.update({
            "q": incoming["q"],
            "t": mess_now().strftime("%H:%M"),
        })
        meal.pop("finePoints", None)
        if incoming.get("optOut"):
            menu = _menu_for(date_value, settings)
            meal["optOut"] = True
            meal["q"] = 0
            meal["finePoints"] = round(_meal_point(menu[short], settings) * 0.5, 2)
            meal["fineReason"] = "Existing opt-out surcharge"
        elif "optOut" in incoming and not incoming["optOut"]:
            meal.pop("optOut", None)

        if meal["q"] <= expected:
            meal["permission"] = {
                "status": "not_required",
                "requested_quantity": 0,
                "approved_quantity": 0,
            }
        elif choice == "with_permission":
            old_permission = previous.get("permission") or {}
            if (
                old_permission.get("status") in {"pending", "approved"}
                and incoming["q"] == previous.get("q")
            ):
                meal["permission"] = old_permission
            else:
                meal["permission"] = {
                    "status": "pending",
                    "choice": choice,
                    "requested_quantity": meal["q"] - expected,
                    "approved_quantity": 0,
                    "requested_at": mess_now().isoformat(),
                }
        elif choice == "without_permission":
            meal["permission"] = {
                "status": "not_requested",
                "choice": choice,
                "requested_quantity": 0,
                "approved_quantity": 0,
            }

        meal = _recalculate_meal(
            meal,
            expected,
            short,
            date_value,
            settings,
            admin_approved=bool(entry.get("adminApproved")),
        )
        meals[short] = meal

    now = mess_now().isoformat()
    confirmed_value = (
        bool(existing.get("confirmed", False))
        if confirmed is None
        else confirmed
    )
    record_data = {
        "user_id": user_id,
        "room": room,
        "date": date_value,
        "writeVersion": 2,
        "meals": meals,
        "confirmed": confirmed_value,
        "confirmed_at": (
            existing.get("confirmed_at")
            if confirmed is None
            else mess_now().strftime("%H:%M") if confirmed else None
        ),
        "updated_at": now,
    }
    record_data.setdefault("created_at", existing.get("created_at", now))
    selector = (
        {"_id": existing["_id"]}
        if existing.get("_id") is not None
        else {"user_id": user_id, "date": date_value, "writeVersion": 2}
    )
    created_at = record_data.pop("created_at")
    collection.update_one(
        selector,
        {
            "$set": record_data,
            "$setOnInsert": {"created_at": created_at},
        },
        upsert=True,
    )
    saved = collection.find_one(selector)
    for short, meal in meals.items():
        if short not in MEAL_FIELDS or not isinstance(meal, dict):
            continue
        if is_meal_cancelled(date_value, short):
            expected = int(entry.get(MEAL_FIELDS[short], entry.get(short, 0)) or 0)
            meals[short] = _recalculate_meal(
                meal,
                expected,
                short,
                date_value,
                settings,
                admin_approved=bool(entry.get("adminApproved")),
            )
    if any(
        is_meal_cancelled(date_value, short)
        for short in meals
        if short in MEAL_FIELDS
    ):
        collection.update_one(
            selector,
            {"$set": {
                "meals": meals,
                "updated_at": mess_now().isoformat(),
            }},
        )
        saved = collection.find_one(selector)
    for short, meal in meals.items():
        permission = meal.get("permission") if isinstance(meal, dict) else None
        if isinstance(permission, dict) and permission.get("status") == "pending":
            dedupe_key = (
                f"permission-{user_id}-{date_value}-{short}-"
                f"{permission.get('requested_at', '')}"
            )
            student = get_user(user_id) or {}
            student_name = student.get("name") or user_id
            get_collection("notifications").update_one(
                {"dedupeKey": dedupe_key},
                {
                    "$setOnInsert": {
                        "title": "Extra meal permission request",
                        "message": (
                            f"{student_name} requested permission for "
                            f"{permission.get('requested_quantity', 0)} extra portion(s)."
                        ),
                        "date": "Just now",
                        "target": "records",
                        "audience": "admins",
                        "dedupeKey": dedupe_key,
                        "created_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
    return _serialize(saved or record_data), None


@meal_records_bp.route("/", methods=["GET"])
@login_required
def get_meal_records_route():
    date_str = request.args.get("date")
    month_str = request.args.get("month")
    if date_str and month_str:
        return jsonify({"success": False, "message": "Specify either date or month, not both"}), 400
    if month_str:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month_str):
            return jsonify({"success": False, "message": "Month must use YYYY-MM format"}), 400
        target_pattern = "^" + re.escape(month_str) + "-"
    elif date_str:
        try:
            if date.fromisoformat(date_str).isoformat() != date_str:
                raise ValueError
        except ValueError:
            return jsonify({"success": False, "message": "Date must use YYYY-MM-DD format"}), 400
        target_pattern = "^" + re.escape(date_str) + "$"
    else:
        target_pattern = "^" + re.escape(mess_now().date().isoformat()) + "$"

    query = {"date": {"$regex": target_pattern}}
    if current_user.role not in APPROVER_ROLES:
        query["user_id"] = current_user.id
    records = get_collection("meal_records").find(query)
    if not isinstance(records, list):
        records = records.sort([
            ("updated_at", -1),
            ("_id", -1),
        ])
    latest_by_user_date = {}
    for record in records:
        key = (str(record.get("user_id") or ""), str(record.get("date") or "")[:10])
        latest_by_user_date.setdefault(key, record)
    result = list(latest_by_user_date.values())
    settings = get_settings() if result else {}
    return jsonify({
        "success": True,
        "records": [
            _record_with_current_calculations(record, settings)
            for record in result
        ],
        "cancellations": list_cancellations(
            date_value=(
                date_str
                if date_str
                else None if month_str
                else mess_now().date().isoformat()
            ),
            month=month_str if month_str else None,
        ),
    })


@meal_records_bp.route("/my-today", methods=["GET"])
@login_required
def get_my_today_record():
    query = {
        "user_id": current_user.id,
        "date": mess_now().date().isoformat(),
    }
    record = get_collection("meal_records").find_one({**query, "writeVersion": 2})
    if not record:
        record = get_collection("meal_records").find_one(query)
    return jsonify({
        "success": True,
        "record": _serialize(record) if record else None,
        "cancellations": list_cancellations(date_value=query["date"]),
    })


@meal_records_bp.route("/", methods=["POST"])
@login_required
def save_meal_record_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {
        "meals", "confirmed", "confirmedAt", "date", "expectedUserId"
    }:
        return jsonify({"success": False, "message": "A valid meal-record object is required."}), 400
    if current_user.role != "student":
        return jsonify({
            "success": False,
            "message": "Only student accounts may submit meal records.",
        }), 403
    expected_user_id = data.get("expectedUserId")
    if expected_user_id is not None:
        if not isinstance(expected_user_id, str) or not expected_user_id.strip():
            return jsonify({
                "success": False,
                "message": "expectedUserId must identify the signed-in student.",
            }), 400
        if expected_user_id.strip().upper() != str(current_user.id).strip().upper():
            return jsonify({
                "success": False,
                "message": "Your signed-in account changed. Refresh and sign in again before saving.",
            }), 409
    date_value = data.get("date", mess_now().date().isoformat())
    try:
        valid_date = (
            isinstance(date_value, str)
            and date.fromisoformat(date_value).isoformat() == date_value
        )
    except ValueError:
        valid_date = False
    if not valid_date:
        return jsonify({"success": False, "message": "Date must use YYYY-MM-DD format."}), 400
    if date_value != mess_now().date().isoformat():
        return jsonify({"success": False, "message": "Students may only save today's meal record."}), 403
    meals = data.get("meals", {})
    if not isinstance(meals, dict):
        return jsonify({"success": False, "message": "Meals must be an object."}), 400
    if not meals:
        return jsonify({"success": False, "message": "At least one meal is required."}), 400
    if "confirmed" in data and not isinstance(data["confirmed"], bool):
        return jsonify({"success": False, "message": "confirmed must be a boolean."}), 400
    if data.get("confirmed") is True and not all(
        meals.get(short) or is_meal_cancelled(date_value, short)
        for short in MEAL_FIELDS
    ):
        return jsonify({
            "success": False,
            "message": "All meals must be saved before confirming the day.",
        }), 400
    if data.get("confirmedAt") is not None and (
        not isinstance(data["confirmedAt"], str)
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", data["confirmedAt"])
    ):
        return jsonify({"success": False, "message": "confirmedAt must use HH:MM format."}), 400
    try:
        record, error = _save_meals(
            current_user.id,
            current_user.room,
            date_value,
            meals,
            confirmed=data.get("confirmed"),
            confirmed_at=data.get("confirmedAt"),
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 503
    except PyMongoError:
        return jsonify({
            "success": False,
            "message": "Meal record could not be saved. Please try again.",
        }), 503
    if error:
        payload, status = error
        return jsonify(payload), status
    return jsonify({"success": True, "record": record})


def _no_food_date(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _no_food_request_view(request_data):
    result = _serialize_no_food_request(request_data)
    user = get_user(request_data.get("user_id")) or {}
    result.update({
        "student_name": user.get("name") or request_data.get("student_name") or request_data.get("user_id"),
        "student_id": request_data.get("user_id"),
        "room": user.get("room") or request_data.get("room") or "",
        "branch": user.get("branch") or request_data.get("branch") or "",
    })
    return result


@meal_records_bp.route("/no-food-requests", methods=["GET"])
@login_required
def get_no_food_requests():
    status = str(request.args.get("status") or "").strip().lower()
    if status and status not in {"pending", "approved", "rejected", "cancelled"}:
        return jsonify({"success": False, "message": "Invalid no-food request status."}), 400
    query = {}
    if status:
        query["status"] = status
    if current_user.role not in APPROVER_ROLES:
        query["user_id"] = current_user.id
    requests = get_collection("no_food_requests").find(query).sort(
        [("requested_at", -1), ("_id", -1)]
    )
    return jsonify({
        "success": True,
        "requests": [_no_food_request_view(item) for item in requests],
    })


@meal_records_bp.route("/no-food-requests", methods=["POST"])
@login_required
def create_no_food_request():
    try:
        return _create_no_food_request()
    except PyMongoError:
        current_app.logger.exception("No-food request database operation failed.")
        return jsonify({
            "success": False,
            "message": "No-food request could not be processed. Please try again.",
        }), 503


def _create_no_food_request():
    if current_user.role in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Administrators cannot submit student no-food requests."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {"date", "meal"}:
        return jsonify({"success": False, "message": "A valid date and meal are required."}), 400
    date_value = data.get("date", mess_now().date().isoformat())
    target_date = _no_food_date(date_value)
    short = _meal_from_request(data.get("meal"))
    if target_date is None:
        return jsonify({"success": False, "message": "Date must use YYYY-MM-DD format."}), 400
    if short not in NO_FOOD_MEALS:
        return jsonify({"success": False, "message": "Meal must be breakfast, lunch, or dinner."}), 400

    settings = get_settings()
    today = mess_now().date()
    if target_date not in {today, tomorrow_date()}:
        return jsonify({"success": False, "message": "No-food requests are limited to today or tomorrow."}), 400
    if target_date == tomorrow_date():
        try:
            if tomorrow_entry_is_closed(settings):
                return jsonify({"success": False, "message": "The cutoff for tomorrow's entry has passed."}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error)}), 503
        entry = _entry_for(current_user.id, date_value)
        if int(entry.get(NO_FOOD_MEALS[short], entry.get(short, 0)) or 0) > 0:
            return jsonify({
                "success": False,
                "message": "A normal mess entry already exists for this meal. Edit it before requesting no food.",
            }), 409
    else:
        close_time = _valid_menu_time(
            settings,
            {"b": "breakfastClose", "l": "lunchClose", "d": "dinnerClose"}[short],
        )
        if mess_now().time().replace(tzinfo=None) >= close_time:
            return jsonify({"success": False, "message": "This meal's cutoff has passed."}), 403

    requests_collection = get_collection("no_food_requests")
    existing = requests_collection.find_one({
        "user_id": current_user.id,
        "date": date_value,
        "meal": short,
    })
    if existing:
        payload = _no_food_request_view(existing)
        existing_status = str(existing.get("status") or "pending").lower()
        if existing_status in {"pending", "approved"}:
            return jsonify({"success": True, "created": False, "request": payload}), 200
        if existing_status == "cancelled":
            # A normal meal entry created after cancellation must take precedence.
            existing_record = get_collection("meal_records").find_one({
                "user_id": current_user.id, "date": date_value,
            })
            existing_meal_data = (existing_record or {}).get("meals", {}).get(short)
            if isinstance(existing_meal_data, dict) and int(existing_meal_data.get("q", 0) or 0) > 0:
                return jsonify({"success": False, "message": "A normal meal entry already exists for this meal; edit it before requesting no food."}), 409
            # Reuse the unique student/date/meal record and reopen it safely.
            now = mess_now().isoformat()
            reopened = requests_collection.find_one_and_update(
                {"_id": existing["_id"], "status": "cancelled"},
                {"$set": {
                    "status": "pending",
                    "requested_at": now,
                    "reviewed_at": None,
                    "reviewed_by": None,
                    "cancelled_at": None,
                    "updated_at": now,
                    "approved_zero_points": False,
                }},
                return_document=ReturnDocument.AFTER,
            )
            if not reopened:
                latest = requests_collection.find_one({"_id": existing["_id"]}) or existing
                return jsonify({"success": False, "message": "This request changed while you were submitting. Refresh and try again.", "request": _no_food_request_view(latest)}), 409
            reopened_view = _no_food_request_view(reopened)
            request_id = str(reopened.get("_id"))
            response = {"success": True, "created": True, "request": reopened_view}
            try:
                get_collection("notifications").update_one(
                    {"dedupeKey": f"no-food-pending-{request_id}-{now}"},
                    {"$setOnInsert": {
                        "title": "No-food request pending",
                        "message": f"{current_user.name or current_user.id} requested no food for {NO_FOOD_MEALS[short]} on {date_value}.",
                        "date": date_value, "target": "entries", "audience": "admins",
                        "dedupeKey": f"no-food-pending-{request_id}-{now}", "created_at": utc_now(),
                    }},
                    upsert=True,
                )
            except PyMongoError:
                current_app.logger.exception(
                    "No-food request was reopened, but its admin notification failed."
                )
                response["warning"] = (
                    "The request was reopened, but its admin notification could not "
                    "be recorded. The active admin queue still reads saved requests."
                )
            return jsonify(response), 200
        return jsonify({
            "success": False,
            "message": "A no-food request for this meal was already reviewed and rejected.",
            "request": payload,
        }), 409

    record = get_collection("meal_records").find_one({
        "user_id": current_user.id,
        "date": date_value,
    })
    saved_meal = (record or {}).get("meals", {}).get(short)
    if isinstance(saved_meal, dict) and int(saved_meal.get("q", 0) or 0) > 0:
        return jsonify({
            "success": False,
            "message": "A normal meal entry already exists for this meal; conflicting no-food state is not allowed.",
        }), 409

    now = mess_now().isoformat()
    request_data = {
        "user_id": current_user.id,
        "room": current_user.room,
        "branch": getattr(current_user, "branch", "") or "",
        "date": date_value,
        "meal": short,
        "meal_type": short,
        "dish_name": _no_food_menu_name(date_value, short, settings),
        "status": "pending",
        "requested_at": now,
        "reviewed_at": None,
        "reviewed_by": None,
        "approved_zero_points": False,
        "created_at": now,
        "updated_at": now,
    }
    try:
        inserted = requests_collection.insert_one(request_data)
    except DuplicateKeyError:
        existing = requests_collection.find_one({
            "user_id": current_user.id,
            "date": date_value,
            "meal": short,
        })
        return jsonify({
            "success": True,
            "created": False,
            "request": _no_food_request_view(existing or request_data),
        }), 200
    if getattr(inserted, "inserted_id", None) is not None:
        request_data["_id"] = inserted.inserted_id
    request_id = str(request_data.get("_id") or f"{current_user.id}-{date_value}-{short}")
    warnings = []
    try:
        get_collection("notifications").update_one(
            {"dedupeKey": f"no-food-pending-{request_id}"},
            {"$setOnInsert": {
                "title": "No-food request pending",
                "message": (
                    f"{current_user.name or current_user.id} requested no food for "
                    f"{NO_FOOD_MEALS[short]} on {date_value}."
                ),
                "date": date_value,
                "target": "entries",
                "audience": "admins",
                "dedupeKey": f"no-food-pending-{request_id}",
                "created_at": utc_now(),
            }},
            upsert=True,
        )
    except PyMongoError:
        current_app.logger.exception(
            "No-food request was saved, but its admin notification failed."
        )
        warnings.append(
            "The request was saved, but its admin notification could not be recorded. "
            "The active admin queue still reads saved requests."
        )
    try:
        saved = requests_collection.find_one({"_id": request_data.get("_id")}) if request_data.get("_id") else request_data
    except PyMongoError:
        current_app.logger.exception(
            "No-food request was saved, but its read-back failed."
        )
        saved = request_data
        warnings.append(
            "The request was saved, but the server could not verify its read-back. "
            "Refresh the page to confirm its status."
        )
    response = {
        "success": True,
        "created": True,
        "request": _no_food_request_view(saved or request_data),
    }
    if warnings:
        response["warning"] = " ".join(warnings)
    return jsonify(response), 201


def _review_no_food_request(request_id, status):
    if current_user.role not in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    if not ObjectId.is_valid(request_id):
        return jsonify({"success": False, "message": "No-food request not found."}), 404
    collection = get_collection("no_food_requests")
    try:
        request_data = collection.find_one({"_id": ObjectId(request_id)})
    except PyMongoError:
        current_app.logger.exception("No-food review request lookup failed.")
        return jsonify({
            "success": False,
            "message": "No-food request could not be loaded. Please retry.",
        }), 503
    if not request_data:
        return jsonify({"success": False, "message": "No-food request not found."}), 404
    if request_data.get("status") != "pending":
        return jsonify({
            "success": False,
            "message": "This no-food request has already been reviewed.",
            "request": _no_food_request_view(request_data),
        }), 409

    short = _meal_from_request(request_data.get("meal"))
    record_collection = get_collection("meal_records")
    try:
        record = record_collection.find_one({
            "user_id": request_data.get("user_id"),
            "date": request_data.get("date"),
        })
    except PyMongoError:
        current_app.logger.exception("No-food review meal-record lookup failed.")
        return jsonify({
            "success": False,
            "message": "The student's meal record could not be checked. No review was started.",
        }), 503
    saved_meal = (record or {}).get("meals", {}).get(short)
    if status == "approved" and isinstance(saved_meal, dict):
        existing_no_food = saved_meal.get("noFood")
        if int(saved_meal.get("q", 0) or 0) > 0 and not (
            isinstance(existing_no_food, dict) and existing_no_food.get("status") == "approved"
        ):
            return jsonify({
                "success": False,
                "message": "The student has a conflicting normal meal entry; approval was not applied.",
            }), 409

    now = mess_now()
    now_text = now.isoformat()
    review_token = str(uuid4())
    state = request_data.get("review_state")
    if state == "syncing":
        try:
            started_at = datetime.fromisoformat(str(request_data.get("review_started_at") or ""))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=now.tzinfo)
        except ValueError:
            started_at = now
        if now - started_at < NO_FOOD_REVIEW_LEASE:
            return jsonify({
                "success": False,
                "message": "This request is already being synchronized. Retry after the current review finishes.",
            }), 409
        claim_selector = {
            "_id": ObjectId(request_id),
            "status": "pending",
            "review_state": "syncing",
            "review_token": request_data.get("review_token"),
        }
    elif state == "failed":
        claim_selector = {
            "_id": ObjectId(request_id),
            "status": "pending",
            "review_state": "failed",
            "review_status": request_data.get("review_status"),
        }
    elif state is None:
        claim_selector = {
            "_id": ObjectId(request_id),
            "status": "pending",
            "review_state": {"$exists": False},
        }
    else:
        return jsonify({
            "success": False,
            "message": "This no-food request has an unresolved review state and requires administrator reconciliation.",
        }), 409

    try:
        claim_result = collection.update_one(
            claim_selector,
            {"$set": {
                "review_state": "syncing",
                "review_status": status,
                "review_token": review_token,
                "review_started_at": now_text,
            }},
        )
    except PyMongoError:
        current_app.logger.exception("No-food review could not claim the request.")
        return jsonify({
            "success": False,
            "message": "No-food review could not be started. The request remains pending.",
        }), 503
    if not isinstance(getattr(claim_result, "matched_count", None), int) or claim_result.matched_count != 1:
        return jsonify({
            "success": False,
            "message": "This request changed or is already being reviewed. Refresh and retry.",
        }), 409

    try:
        existing_meal = (record or {}).get("meals", {}).get(short)
        meal = dict(existing_meal) if isinstance(existing_meal, dict) else {}
        if status == "approved" or int(meal.get("q", 0) or 0) <= 0:
            meal["q"] = 0
            meal["t"] = now_text
        meal["noFood"] = {
            "status": status,
            "request_id": request_id,
            "review_state": "syncing",
            "reviewed_by": current_user.id,
            "reviewed_at": now_text,
            "dish_name": request_data.get("dish_name") or "",
        }
        record_selector = {
            "user_id": request_data.get("user_id"),
            "date": request_data.get("date"),
        }
        record_result = record_collection.update_one(
            record_selector,
            {"$set": {
                "writeVersion": 2,
                f"meals.{short}": meal,
                "updated_at": now_text,
            }, "$setOnInsert": {
                "user_id": request_data.get("user_id"),
                "room": request_data.get("room") or "",
                "date": request_data.get("date"),
                "created_at": now_text,
                "confirmed": False,
                "confirmed_at": None,
            }},
            upsert=True,
        )
        if not _write_was_applied(record_result):
            raise RuntimeError("The meal-record update was not acknowledged.")

        entry_collection = get_collection("mess_entries")
        entry_result = entry_collection.update_many(
            record_selector,
            {"$set": {
                f"noFoodMeals.{short}": {
                    "status": status,
                    "request_id": request_id,
                    "review_state": "syncing",
                    "dish_name": request_data.get("dish_name") or "",
                    "reviewed_at": now_text,
                    "reviewed_by": current_user.id,
                },
                "updated_at": now_text,
            }, "$setOnInsert": {
                "user_id": request_data.get("user_id"),
                "room": request_data.get("room") or "",
                "date": request_data.get("date"),
                "created_at": now_text,
            }},
            upsert=True,
        )
        if not _write_was_applied(entry_result):
            raise RuntimeError("The mess-entry marker update was not acknowledged.")

        staged_record = record_collection.find_one(record_selector)
        if not isinstance(staged_record, dict):
            raise RuntimeError("The staged meal record could not be read back.")
        recalculate_existing_meal_record(
            str(request_data.get("user_id") or ""),
            str(request_data.get("date") or ""),
            record=staged_record,
        )
        marker_selector = {
            **record_selector,
            f"meals.{short}.noFood.request_id": request_id,
            f"meals.{short}.noFood.review_state": "syncing",
        }
        record_marker_result = record_collection.update_one(
            marker_selector,
            {"$set": {
                f"meals.{short}.noFood.review_state": "complete",
                "updated_at": now_text,
            }},
        )
        if not _write_was_applied(record_marker_result):
            raise RuntimeError("The meal-record review marker could not be finalized.")

        entry_marker_result = entry_collection.update_many(
            {
                **record_selector,
                f"noFoodMeals.{short}.request_id": request_id,
                f"noFoodMeals.{short}.review_state": "syncing",
            },
            {"$set": {
                f"noFoodMeals.{short}.review_state": "complete",
                "updated_at": now_text,
            }},
        )
        if not _write_was_applied(entry_marker_result):
            raise RuntimeError("The mess-entry review marker could not be finalized.")

        final_update = {
            "status": status,
            "reviewed_by": current_user.id,
            "reviewed_at": now_text,
            "updated_at": now_text,
            "approved_zero_points": status == "approved",
            "review_state": "complete",
        }
        updated = collection.find_one_and_update(
            {
                "_id": ObjectId(request_id),
                "status": "pending",
                "review_state": "syncing",
                "review_token": review_token,
            },
            {"$set": final_update, "$unset": {
                "review_token": "",
                "review_started_at": "",
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not isinstance(updated, dict) or updated.get("status") != status:
            raise RuntimeError("The pending review changed before its final status could be committed.")
    except (PyMongoError, ValueError, RuntimeError) as error:
        current_app.logger.exception(
            "No-food review synchronization failed; the request remains pending and retryable."
        )
        try:
            failed_result = collection.update_one(
                {
                    "_id": ObjectId(request_id),
                    "status": "pending",
                    "review_state": "syncing",
                    "review_token": review_token,
                },
                {"$set": {
                    "review_state": "failed",
                    "review_failed_at": mess_now().isoformat(),
                    "review_failure": "Related records could not be synchronized.",
                }, "$unset": {
                    "review_token": "",
                    "review_started_at": "",
                }},
            )
            if getattr(failed_result, "matched_count", 0) != 1:
                current_app.logger.error(
                    "Failed to release no-food review claim; lease expiry permits safe retry."
                )
        except PyMongoError:
            current_app.logger.exception(
                "Failed to mark no-food review as retryable; lease expiry permits safe retry."
            )
        try:
            latest = collection.find_one({"_id": ObjectId(request_id)})
        except PyMongoError:
            current_app.logger.exception(
                "Could not read back the no-food review outcome after synchronization failure."
            )
            latest = None
        if (
            isinstance(latest, dict)
            and latest.get("status") == status
            and latest.get("review_state") == "complete"
        ):
            response = {"success": True, "request": _serialize_no_food_request(latest)}
            try:
                _no_food_notification(latest, status)
            except PyMongoError:
                current_app.logger.exception(
                    "No-food review completed, but its notification could not be recorded."
                )
                response["warning"] = (
                    "The review was saved, but its notification could not be recorded."
                )
            return jsonify(response)
        return jsonify({
            "success": False,
            "message": (
                "No-food review was not completed. Refresh the request status before retrying; "
                "any partial record writes are explicitly marked for administrator reconciliation."
            ),
            "retryable": isinstance(latest, dict) and latest.get("status") == "pending",
            "request": _serialize_no_food_request(latest) if isinstance(latest, dict) else None,
        }), 503

    response = {"success": True}
    try:
        response["request"] = _no_food_request_view(updated)
    except PyMongoError:
        current_app.logger.exception(
            "No-food review completed, but student details could not be loaded."
        )
        response["request"] = _serialize_no_food_request(updated)
        response["warning"] = (
            "The review was saved, but student details could not be refreshed."
        )
    try:
        _no_food_notification(updated, status)
    except PyMongoError:
        current_app.logger.exception(
            "No-food review completed, but its notification could not be recorded."
        )
        notification_warning = (
            "The review was saved, but its notification could not be recorded."
        )
        response["warning"] = " ".join(
            value for value in (response.get("warning"), notification_warning) if value
        )
    return jsonify(response)


def _write_was_applied(result):
    if getattr(result, "acknowledged", True) is False:
        return False
    matched = getattr(result, "matched_count", None)
    upserted = getattr(result, "upserted_id", None)
    if isinstance(matched, int) and matched > 0:
        modified = getattr(result, "modified_count", None)
        return isinstance(modified, int) and 0 <= modified <= matched
    return upserted is not None


@meal_records_bp.route("/no-food-requests/<request_id>", methods=["DELETE"])
@login_required
def cancel_no_food_request(request_id):
    """Allow a student to withdraw only their own still-pending no-food request."""
    if not ObjectId.is_valid(request_id):
        return jsonify({"success": False, "message": "No-food request not found."}), 404
    if current_user.role in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Only the requesting student can cancel a no-food request."}), 403
    collection = get_collection("no_food_requests")
    try:
        existing = collection.find_one({"_id": ObjectId(request_id)})
    except PyMongoError:
        current_app.logger.exception("No-food cancellation lookup failed.")
        return jsonify({
            "success": False,
            "message": "No-food request could not be loaded. Please try again.",
        }), 503
    if not existing:
        return jsonify({"success": False, "message": "No-food request not found."}), 404
    if existing.get("user_id") != current_user.id:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    if existing.get("status") != "pending":
        return jsonify({"success": False, "message": "Only pending requests can be cancelled."}), 409
    if existing.get("review_state"):
        return jsonify({
            "success": False,
            "message": "This pending request is being reconciled by an administrator and cannot be cancelled yet.",
        }), 409

    query = {
        "_id": ObjectId(request_id),
        "status": "pending",
        "user_id": current_user.id,
        "review_state": {"$exists": False},
    }
    now = mess_now().isoformat()
    try:
        result = collection.update_one(query, {"$set": {
            "status": "cancelled",
            "cancelled_at": now,
            "updated_at": now,
            "approved_zero_points": False,
        }})
    except PyMongoError:
        current_app.logger.exception("No-food cancellation update failed.")
        return jsonify({
            "success": False,
            "message": "No-food request could not be cancelled. Please try again.",
        }), 503
    if not getattr(result, "matched_count", 0):
        return jsonify({
            "success": False,
            "message": "This request changed before it could be cancelled. Refresh and try again.",
        }), 409
    cancelled = {
        **existing,
        "status": "cancelled",
        "cancelled_at": now,
        "updated_at": now,
        "approved_zero_points": False,
    }
    return jsonify({
        "success": True,
        "message": "No-food request cancelled. Admin approval/rejection is no longer available.",
        "request": _serialize_no_food_request(cancelled),
    })


@meal_records_bp.route("/no-food-requests/<request_id>/approve", methods=["POST"])
@login_required
def approve_no_food_request(request_id):
    return _review_no_food_request(request_id, "approved")


@meal_records_bp.route("/no-food-requests/<request_id>/reject", methods=["POST"])
@login_required
def reject_no_food_request(request_id):
    return _review_no_food_request(request_id, "rejected")


@meal_records_bp.route("/permissions/pending", methods=["GET"])
@login_required
def get_pending_meal_permissions():
    if current_user.role not in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    query = {"meals": {"$exists": True}}
    records = get_collection("meal_records").find(query).sort("updated_at", -1)
    result = []
    for record in records:
        pending = {
            short: meal
            for short, meal in (record.get("meals") or {}).items()
            if isinstance(meal, dict)
            and isinstance(meal.get("permission"), dict)
            and meal["permission"].get("status") == "pending"
        }
        if pending:
            item = _serialize(record)
            item["pendingPermissions"] = pending
            user = get_collection("users").find_one(
                {"id": record.get("user_id")},
                {"name": 1, "room": 1},
            ) or {}
            item["user_name"] = user.get("name") or record.get("user_id")
            item["room"] = user.get("room") or record.get("room")
            result.append(item)
    return jsonify({"success": True, "requests": result})


@meal_records_bp.route("/permissions/<record_id>/<short>", methods=["POST"])
@login_required
def decide_meal_permission(record_id, short):
    if current_user.role not in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    if not ObjectId.is_valid(record_id) or short not in MEAL_FIELDS:
        return jsonify({"success": False, "message": "Permission request not found."}), 404
    collection = get_collection("meal_records")
    record = collection.find_one({"_id": ObjectId(record_id)})
    if not record:
        return jsonify({"success": False, "message": "Permission request not found."}), 404
    if str(record.get("user_id") or "").upper() == str(current_user.id).upper():
        return jsonify({"success": False, "message": "You cannot approve your own permission request."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("status"), str) or data.get("status") not in {"approved", "rejected"}:
        return jsonify({"success": False, "message": "status must be approved or rejected."}), 400
    meal = (record.get("meals") or {}).get(short)
    if is_meal_cancelled(record["date"], short):
        recalculate_existing_meal_record(record["user_id"], record["date"])
        return jsonify({
            "success": False,
            "message": "This meal was cancelled and its permission cannot be approved.",
        }), 409
    permission = meal.get("permission") if isinstance(meal, dict) else None
    if not isinstance(permission, dict) or permission.get("status") != "pending":
        return jsonify({"success": False, "message": "This permission request is no longer pending."}), 409
    permission = dict(permission)
    permission.update({
        "status": data["status"],
        "decided_by": current_user.id,
        "decided_at": mess_now().isoformat(),
        "approved_quantity": (
            permission.get("requested_quantity", 0)
            if data["status"] == "approved"
            else 0
        ),
    })
    meal["permission"] = permission
    settings = get_settings()
    entry = _entry_for(record["user_id"], record["date"])
    expected = int(entry.get(MEAL_FIELDS[short], entry.get(short, 0)) or 0)
    meal = _recalculate_meal(
        meal,
        expected,
        short,
        record["date"],
        settings,
        admin_approved=bool(entry.get("adminApproved")),
    )
    collection.update_one(
        {"_id": ObjectId(record_id)},
        {"$set": {f"meals.{short}": meal, "updated_at": mess_now().isoformat()}},
    )
    updated = collection.find_one({"_id": ObjectId(record_id)})
    return jsonify({"success": True, "record": _serialize(updated or record)})


@meal_records_bp.route("/<record_id>", methods=["PUT"])
@login_required
def update_meal_record_route(record_id):
    if not ObjectId.is_valid(record_id):
        return jsonify({"success": False, "message": "Record not found."}), 404
    collection = get_collection("meal_records")
    record = collection.find_one({"_id": ObjectId(record_id)})
    if not record:
        return jsonify({"success": False, "message": "Record not found."}), 404
    is_approver = current_user.role in APPROVER_ROLES
    if not is_approver and record.get("user_id") != current_user.id:
        return jsonify({"success": False, "message": "Record not found."}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {"meals", "confirmed", "confirmedAt"}:
        return jsonify({"success": False, "message": "Invalid meal-record fields."}), 400
    meals = data.get("meals")
    if meals is not None and not isinstance(meals, dict):
        return jsonify({"success": False, "message": "Meals must be an object."}), 400
    if "confirmed" in data and not isinstance(data["confirmed"], bool):
        return jsonify({"success": False, "message": "confirmed must be a boolean."}), 400
    if "confirmedAt" in data and data["confirmedAt"] is not None and (
        not isinstance(data["confirmedAt"], str)
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", data["confirmedAt"])
    ):
        return jsonify({"success": False, "message": "confirmedAt must use HH:MM format."}), 400
    if meals:
        try:
            updated, error = _save_meals(
                record["user_id"],
                record.get("room", ""),
                record["date"],
                meals,
                admin=is_approver,
                record=record,
                confirmed=data.get("confirmed"),
                confirmed_at=data.get("confirmedAt"),
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error)}), 503
        except PyMongoError:
            return jsonify({
                "success": False,
                "message": "Meal record could not be saved. Please try again.",
            }), 503
        if error:
            payload, status = error
            return jsonify(payload), status
        return jsonify({"success": True, "record": updated})
    if not any(key in data for key in ("confirmed", "confirmedAt")):
        return jsonify({"success": False, "message": "At least one field is required."}), 400

    updates = {}
    if "confirmed" in data:
        updates["confirmed"] = data["confirmed"]
        updates["confirmed_at"] = (
            mess_now().strftime("%H:%M") if data["confirmed"] else None
        )
    if "confirmedAt" in data:
        if "confirmed" not in data:
            return jsonify({
                "success": False,
                "message": "confirmedAt can only change with confirmed status.",
            }), 400
    if updates:
        collection.update_one({"_id": ObjectId(record_id)}, {"$set": updates})
    return jsonify({"success": True, "record": record})


@meal_records_bp.route("/cancellations", methods=["GET"])
@login_required
def get_meal_cancellations():
    date_value = request.args.get("date")
    month = request.args.get("month")
    if date_value and month:
        return jsonify({
            "success": False,
            "message": "Specify either date or month, not both.",
        }), 400
    if date_value:
        try:
            if date.fromisoformat(date_value).isoformat() != date_value:
                raise ValueError
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Date must use YYYY-MM-DD format.",
            }), 400
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        return jsonify({
            "success": False,
            "message": "Month must use YYYY-MM format.",
        }), 400
    if not date_value and not month:
        date_value = mess_now().date().isoformat()
    return jsonify({
        "success": True,
        "cancellations": list_cancellations(date_value=date_value, month=month),
    })


@meal_records_bp.route("/cancellations", methods=["POST"])
@login_required
def cancel_meal():
    if current_user.role not in APPROVER_ROLES:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {
        "date", "meal", "reason", "confirmRetroactive"
    }:
        return jsonify({
            "success": False,
            "message": "A valid cancellation request is required.",
        }), 400
    date_value = data.get("date")
    try:
        if (
            not isinstance(date_value, str)
            or date.fromisoformat(date_value).isoformat() != date_value
        ):
            raise ValueError
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Date must use YYYY-MM-DD format.",
        }), 400
    short = {
        "b": "b", "breakfast": "b",
        "l": "l", "lunch": "l",
        "d": "d", "dinner": "d",
    }.get(str(data.get("meal") or "").strip().lower())
    if not short:
        return jsonify({
            "success": False,
            "message": "Meal must be breakfast, lunch, or dinner.",
        }), 400
    reason = data.get("reason", "")
    if not isinstance(reason, str) or len(reason.strip()) > 500:
        return jsonify({
            "success": False,
            "message": "Reason must be 500 characters or fewer.",
        }), 400


    settings = get_settings()
    now = mess_now()
    close_time = _valid_menu_time(
        settings,
        {"b": "breakfastClose", "l": "lunchClose", "d": "dinnerClose"}[short],
    )
    target_date = date.fromisoformat(date_value)
    is_retroactive = target_date < now.date() or (
        target_date == now.date()
        and now.time().replace(tzinfo=None) >= close_time
    )
    if is_retroactive and data.get("confirmRetroactive") is not True:
        return jsonify({
            "success": False,
            "message": "Explicit confirmation is required for a past or already-served meal.",
            "requiresRetroactiveConfirmation": True,
        }), 409

    meal_name = MEAL_FIELDS[short]
    cancellation_data = {
        "date": date_value,
        "meal_type": short,
        "status": "cancelled",
        "reason": reason.strip(),
        "cancelled_by": current_user.id,
        "cancelled_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "retroactive": is_retroactive,
    }
    cancellation_collection = get_collection("meal_cancellations")
    try:
        save_result = cancellation_collection.update_one(
            {"date": date_value, "meal_type": short},
            {"$setOnInsert": cancellation_data},
            upsert=True,
        )
    except DuplicateKeyError:
        save_result = None
    cancellation = cancellation_collection.find_one({
        "date": date_value,
        "meal_type": short,
        "status": "cancelled",
    })
    if not cancellation:
        return jsonify({
            "success": False,
            "message": "The cancellation could not be saved.",
        }), 503

    cancellation_id = str(cancellation.get("_id") or "")
    created = bool(save_result and save_result.upserted_id)
    if created:
        date_label = target_date.strftime("%d %B %Y")
        dedupe_key = f"meal-cancel-{date_value}-{short}"
        get_collection("notifications").update_one(
            {"dedupeKey": dedupe_key},
            {"$setOnInsert": {
                "title": f"{meal_name.capitalize()} Cancelled",
                "message": (
                    f"{meal_name.capitalize()} for {date_label} has been cancelled "
                    "by the hostel administration. No meal points or meal-related "
                    "fines will be charged for this meal."
                ),
                "date": "Just now",
                "target": "notifs",
                "audience": "students",
                "dedupeKey": dedupe_key,
                "created_at": now.astimezone(timezone.utc),
            }},
            upsert=True,
        )

    for record in get_collection("meal_records").find({"date": date_value}):
        recalculate_existing_meal_record(
            record.get("user_id"),
            date_value,
            record=record,
        )

    apply_meal_cancellation_to_bills(date_value[:7], cancellation_id, cancellation)
    return jsonify({
        "success": True,
        "created": created,
        "cancellation": _serialize(cancellation),
    })

login_manager = LoginManager()
_PRODUCTION_SECRET_PLACEHOLDERS = (
    "change-me",
    "changeme",
    "development",
    "placeholder",
    "replace_with_",
    "test-only",
    "your-secret",
)


def _is_strong_production_secret(secret):
    return (
        isinstance(secret, str)
        and len(secret) >= 32
        and len(set(secret)) >= 16
        and secret == secret.strip()
        and not any(
            placeholder in secret.lower()
            for placeholder in _PRODUCTION_SECRET_PLACEHOLDERS
        )
    )


def _reuses_local_development_secret(secret):
    local_secret = None
    if (ROOT / ".env").exists():
        local_secret = dotenv_values(ROOT / ".env").get("FLASK_SECRET_KEY")
    return (
        isinstance(local_secret, str)
        and bool(local_secret)
        and compare_digest(secret.encode("utf-8"), local_secret.encode("utf-8"))
    )


def _is_production_origin(origin):
    try:
        parsed = urlsplit(origin)
        port = parsed.port
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        return False


def _validate_mongodb_uri(uri, is_production):
    try:
        parsed = urlsplit(uri)
        options = {
            key.lower(): value.strip().lower()
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        }
    except ValueError:
        raise ValueError("MONGODB_URI must be a valid MongoDB URI.") from None

    if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.netloc:
        raise ValueError("MONGODB_URI must use mongodb:// or mongodb+srv://.")

    insecure_true_values = {"true", "1", "yes", "on"}
    for option in (
        "tlsinsecure",
        "sslinsecure",
        "tlsallowinvalidcertificates",
        "tlsallowinvalidhostnames",
    ):
        if options.get(option) in insecure_true_values:
            raise ValueError("MONGODB_URI must not disable TLS certificate verification.")
    if options.get("sslvalidate") in {"false", "0", "no", "off"}:
        raise ValueError("MONGODB_URI must not disable TLS certificate verification.")

    configured_tls = options.get("tls", options.get("ssl"))
    if configured_tls in {"false", "0", "no", "off"}:
        raise ValueError("MONGODB_URI must not disable TLS.")
    if is_production and parsed.scheme != "mongodb+srv" and configured_tls not in {
        "true",
        "1",
        "yes",
        "on",
    }:
        raise ValueError("Production MONGODB_URI must enable TLS.")

    return parsed.scheme == "mongodb+srv" or is_production


def _connection_failure_category(error):
    if isinstance(error, ConfigurationError):
        message = str(error).lower()
        if "dns" in message or "_mongodb._tcp" in message:
            return "srv_dns_failure"
        return "invalid_mongodb_uri"
    if isinstance(error, ServerSelectionTimeoutError):
        message = str(error).lower()
        if "ssl" in message or "tls" in message:
            return "tls_handshake"
        return "server_selection_timeout"
    if isinstance(error, ConnectionFailure):
        return "connection_failure"
    return "database_error"


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({
        "success": False,
        "message": "Authentication required"
    }), 401


@login_manager.user_loader
def load_user(user_id):
    user_data = get_user(user_id)
    if not user_data:
        return None
    if user_data.get("status") != "active":
        return None
    if int(session.get("auth_version") or 0) != int(user_data.get("auth_version") or 0):
        return None
    return User(user_data)


def create_app(config_name="default"):
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config.from_object(config[config_name])
    is_production = config_name == "production"
    secret_key = app.config.get("SECRET_KEY")

    if not secret_key:
        if is_production:
            raise ValueError(
                "Production FLASK_SECRET_KEY must be supplied by the deployment environment."
            )
        raise ValueError(
            "FLASK_SECRET_KEY must be configured in the environment or app config."
        )
    if is_production and not _is_strong_production_secret(secret_key):
        raise ValueError(
            "Production FLASK_SECRET_KEY must be a deployment secret with at least "
            "32 characters and 16 distinct characters; replace development placeholders."
        )
    if is_production and _reuses_local_development_secret(secret_key):
        raise ValueError(
            "Production FLASK_SECRET_KEY must not reuse the local development secret."
        )

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_PATH="/",
    )

    configured_origins = app.config.get("FRONTEND_ORIGIN")
    if not configured_origins:
        if not app.debug:
            raise ValueError("FRONTEND_ORIGIN must be configured for production.")
        configured_origins = "http://localhost:5000"

    origin_values = [origin.strip() for origin in configured_origins.split(",")]
    origins = [origin.rstrip("/") for origin in origin_values if origin]

    if is_production and (
        len(origins) != len(origin_values)
        or not origins
        or any(not _is_production_origin(origin) for origin in origins)
    ):
        raise ValueError(
            "Production FRONTEND_ORIGIN must contain exact HTTPS origins without paths, "
            "queries, or fragments."
        )

    mongo_uri = app.config.get("MONGODB_URI")
    if not isinstance(mongo_uri, str) or not mongo_uri.strip():
        raise ValueError("MONGODB_URI must be configured in the environment or app config.")

    database_name = app.config.get("MONGODB_DATABASE")
    if not isinstance(database_name, str) or not database_name.strip():
        raise ValueError("MONGODB_DATABASE is not configured.")
    use_tls = _validate_mongodb_uri(mongo_uri, is_production)

    if app.debug:
        origins.extend([
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
        ])

    origins = list(dict.fromkeys(origins))
    CORS(
        app,
        origins=origins,
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.config["CORS_ALLOWED_ORIGINS"] = origins

    mongo_options = {
        "connect": False,
        "connectTimeoutMS": 5000,
        "serverSelectionTimeoutMS": 5000,
        "waitQueueTimeoutMS": 5000,
        "maxPoolSize": 10,
        "minPoolSize": 0,
        "maxIdleTimeMS": 30000,
        "tlsCAFile": certifi.where(),
    }
    if use_tls:
        mongo_options["tls"] = True

    def initialize_database():
        if app.extensions.get("mma_mongo_initialized"):
            return
        try:
            mongo.init_app(app, uri=mongo_uri, **mongo_options)
            mongo.db = mongo.cx[database_name]
        except ConfigurationError as error:
            raise MongoInitializationError(
                _connection_failure_category(error)
            ) from None
        app.extensions["mma_mongo_initialized"] = True

    def unavailable_database_response(failure_category):
        return jsonify({
            "application": "available",
            "database": "disconnected",
            "database_name": database_name,
            "connection_failure_category": failure_category,
        }), 503

    @app.cli.command("ensure-indexes")
    def ensure_indexes_command():
        """Run the additive MongoDB index migration explicitly."""
        try:
            initialize_database()
            mongo.db.command("ping")
            ensure_indexes(app)
        except (MongoInitializationError, PyMongoError) as error:
            error_category = (
                error.category
                if isinstance(error, MongoInitializationError)
                else (
                    _connection_failure_category(error)
                    if isinstance(error, ConnectionFailure)
                    else type(error).__name__
                )
            )
            app.logger.error("MongoDB index migration failed (%s).", error_category)
            raise ClickException(
                f"MongoDB index migration failed ({error_category}); "
                "no application records were changed."
            ) from None

    @app.before_request
    def validate_request_origin():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        origin = request.headers.get("Origin")
        if not origin:
            return None
        allowed_origins = app.config.get("CORS_ALLOWED_ORIGINS", [])
        if isinstance(allowed_origins, str):
            allowed_origins = allowed_origins.split(",")
        allowed_origins = {
            item.strip().rstrip("/")
            for item in allowed_origins
            if item and item.strip()
        }
        origin = origin.strip().rstrip("/")
        same_origin = request.host_url.rstrip("/")
        if origin not in allowed_origins and origin != same_origin:
            app.logger.warning("Rejected request origin: %s", origin)
            return jsonify({
                "success": False,
                "message": "Request origin is not allowed",
            }), 403
        return None

    @app.before_request
    def initialize_database_for_request():
        has_login_session = bool(
            session.get("_user_id")
            or request.cookies.get(app.config.get("REMEMBER_COOKIE_NAME", "remember_token"))
        )
        public_endpoint = request.endpoint in {
            "static",
            "home",
            "admin_page",
            "student_page",
            "favicon",
        }
        if not has_login_session and (
            request.method == "OPTIONS"
            or request.endpoint is None
            or public_endpoint
        ):
            return None
        initialize_database()

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(menu_bp, url_prefix="/api/menu")
    app.register_blueprint(entries_bp, url_prefix="/api/entries")
    app.register_blueprint(meal_records_bp, url_prefix="/api/meal-records")
    app.register_blueprint(bills_bp, url_prefix="/api/bills")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/admin")
    def admin_page():
        return render_template("admin.html")

    @app.route("/student")
    def student_page():
        return render_template("student.html")

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/health")
    def health_check():
        try:
            mongo.db.command("ping")
        except PyMongoError as error:
            failure_category = _connection_failure_category(error)
            app.logger.warning("MongoDB health check failed (%s).", failure_category)
            return unavailable_database_response(failure_category)
        return jsonify({
            "application": "available",
            "database": "connected",
            "database_name": database_name,
            "connection_failure_category": None,
        }), 200

    @app.errorhandler(ConnectionFailure)
    def database_unavailable(error):
        failure_category = _connection_failure_category(error)
        app.logger.warning("MongoDB request failed (%s).", failure_category)
        return unavailable_database_response(failure_category)

    @app.errorhandler(MongoInitializationError)
    def database_initialization_unavailable(error):
        app.logger.warning(
            "MongoDB initialization failed (%s).",
            error.category,
        )
        return unavailable_database_response(error.category)

    return app


config_name = os.environ.get("FLASK_CONFIG")
if os.environ.get("VERCEL") and config_name != "production":
    raise RuntimeError("Set FLASK_CONFIG=production in the Vercel environment.")
config_name = config_name or "development"
app = create_app(config_name)

if __name__ == "__main__":
    app.run(
        debug=app.debug,
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )

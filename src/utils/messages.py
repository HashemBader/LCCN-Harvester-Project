"""
Module: messages.py
Purpose: Central repository for all application text strings.
         Ensures consistency across Logs, UI, and Errors.
"""

# how to use this module
"""
 import messages
 messages.SystemMessages.app_start
 messages.DatabaseMessages.record_found.format(isbn="1234567890")

"""

class SystemMessages:
    """General system lifecycle messages."""
    app_start = "LCCN Harvester Application started."
    app_close = "Application shutting down."
    config_loaded = "User configuration loaded successfully."
    config_error = "Failed to load configuration: {error}"


class DatabaseMessages:
    """Messages related to SQLite operations."""
    connecting = "Connecting to local database..."
    connect_success = "Successfully connected to SQLite database."
    connect_fail = "Critical Error: Could not connect to database. {error}"
    
    # Dynamic messages (use .format() to fill in data)
    record_found = "Found existing record for ISBN {isbn}."
    insert_success = "Saved record: ISBN {isbn} -> LCCN {lccn}"
    insert_fail = "Failed to save record for ISBN {isbn}: {error}"


class NetworkMessages:
    """Messages for API and Z39.50 interactions."""
    # Status Updates
    connecting_to_target = "Connecting to target: {target}..."
    searching = "Searching for ISBN: {isbn}..."

    # Outcomes
    success_match = "Match found in {target}. Call Number: {call_number}"
    no_match = "No records found in {target}."
    connection_timeout = "Connection to {target} timed out after {seconds}s."
    protocol_error = "Z39.50 Protocol Error with {target}: {error}"

    # Z39.50 specific
    z3950_unavailable = "Z39.50 support not available - install PyZ3950"
    z3950_not_available_detail = "Z39.50 client not available: {error}"
    z3950_lookup_failed = "Z39.50 lookup failed for {isbn} on {target}: {error}"

    # API specific
    api_not_implemented = "API not yet implemented"

    # Data extraction
    record_no_lccn = "Record found but no LCCN field"


class GuiMessages:
    """User-facing messages for the Status Bar and Popups."""
    ready = "Ready"
    processing = "Processing {current}/{total} items..."
    completed = "Harvesting complete. Found {success} matches."

    # Error Dialog Titles/Bodies
    err_title_file = "File Error"
    err_body_file = "Could not open the selected file. Please check permissions."

    warn_title_invalid = "Invalid ISBNs"
    warn_body_invalid = "The input file contained {count} invalid ISBNs. Check logs for details."

    # Input validation
    err_title_no_input = "No Input File"
    err_body_no_input = "Please select an input file before starting a harvest."
    err_title_no_valid_isbns = "No Valid ISBNs"
    err_body_no_valid_isbns = "No valid ISBNs were found in the selected file."


class HarvestMessages:
    """Messages for harvest operations."""
    # Status updates
    starting = "Starting harvest..."
    no_valid_isbns = "No valid ISBNs found in input file"
    harvest_completed = "Harvest completed - {successes} found, {failures} failed"

    # Progress updates
    processing_isbn = "Starting..."
    found_in_cache = "Found in cache"
    skipped_recent_failure = "Skipped (recent failure)"
    checking_target = "Checking {target}..."
    lccn_found = "LCCN: {lccn}"

    # Errors
    error_reading_file = "Error reading file: {error}"
    invalid_isbn_skipped = "Invalid ISBN skipped: {isbn}"
    invalid_isbns_count = "Skipped {count} invalid ISBN(s)"
    failed_create_target = "Warning: Failed to create target {name}: {error}"
    error_building_targets = "Error building targets: {error}"


class ConfigMessages:
    """Messages related to configuration management."""
    target_added = "Added target: {name}"
    target_modified = "Modified target: {name}"
    target_deleted = "Deleted target ID: {target_id}"
    target_not_found = "Target with ID {target_id} not found."
    load_error = "Error loading targets: {error}"
    save_error = "Error saving targets: {error}"

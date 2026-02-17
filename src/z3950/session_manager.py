"""
Module: session_manager.py
Part of the LCCN Harvester Project.
Purpose: Manages Z39.50 sessions and connection validation.
"""

import socket
import logging

def validate_connection(host: str, port: int, timeout: int = 5, silent: bool = False) -> bool:
    """
    Validates that a TCP connection can be established to the given host and port.
    
    Args:
        host (str): The hostname or IP address of the Z39.50 server.
        port (int): The port number (usually 210).
        timeout (int): Connection timeout in seconds.
        silent (bool): If True, suppress warning messages.
        
    Returns:
        bool: True if connection successful, False otherwise.
    """
    try:
        # Create a TCP socket
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, socket.error, ValueError) as e:
        if not silent:
            logging.warning(f"Connection validation failed for {host}:{port} - {e}")
        return False

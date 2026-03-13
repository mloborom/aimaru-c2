"""
In-Memory AMSI Status Tracker
==============================

Tracks AMSI bypass status per client session.
AMSI bypass only works within a PowerShell session - when the session closes, AMSI resets.

This module provides:
- Session-based AMSI status tracking
- Auto-detection from script output
- API for checking client AMSI status
"""
from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta
import threading
import re

class AMSIStatusTracker:
    """Thread-safe in-memory tracker for client AMSI bypass status"""
    
    def __init__(self):
        self._status: Dict[str, dict] = {}
        self._lock = threading.Lock()
        # Patterns that indicate successful AMSI bypass
        self._success_patterns = [
            r"AMSI.*Patched",
            r"AMSI.*bypassed",
            r"bypass.*successful",
            r"\[.*\+.*\].*AMSI",  # [+] AMSI indicators
        ]
    
    def mark_bypassed(self, client_id: str, instruction_id: Optional[str] = None):
        """Mark a client as having AMSI bypassed in current session"""
        with self._lock:
            self._status[client_id] = {
                "bypassed": True,
                "timestamp": datetime.now(timezone.utc),
                "instruction_id": instruction_id
            }
    
    def mark_active(self, client_id: str):
        """Mark AMSI as active (not bypassed) for a client"""
        with self._lock:
            if client_id in self._status:
                del self._status[client_id]
    
    def is_bypassed(self, client_id: str, ttl_minutes: int = 30) -> bool:
        """
        Check if AMSI is currently bypassed for a client
        
        Args:
            client_id: Client identifier
            ttl_minutes: Time-to-live for bypass status (auto-expire after this time)
        
        Returns:
            True if AMSI is bypassed and status hasn't expired
        """
        with self._lock:
            if client_id not in self._status:
                return False
            
            status = self._status[client_id]
            timestamp = status["timestamp"]
            
            # Check if status has expired (session likely ended)
            if datetime.now(timezone.utc) - timestamp > timedelta(minutes=ttl_minutes):
                del self._status[client_id]
                return False
            
            return status["bypassed"]
    
    def get_status(self, client_id: str) -> dict:
        """Get full AMSI status for a client"""
        with self._lock:
            if client_id not in self._status:
                return {"bypassed": False}
            
            status = self._status[client_id].copy()
            # Check TTL
            if datetime.now(timezone.utc) - status["timestamp"] > timedelta(minutes=30):
                del self._status[client_id]
                return {"bypassed": False}
            
            return status
    
    def detect_from_output(self, output: str) -> bool:
        """
        Detect if AMSI bypass was successful from script output
        
        Args:
            output: PowerShell script output
        
        Returns:
            True if bypass indicators found in output
        """
        if not output:
            return False
        
        output_lower = output.lower()
        
        # Check for success patterns
        for pattern in self._success_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True
        
        # Check for specific success messages from our script
        if "amsi" in output_lower and ("patched" in output_lower or "bypass" in output_lower):
            # Ensure it's not an error message
            if "error" not in output_lower and "failed" not in output_lower:
                return True
        
        return False
    
    def cleanup_expired(self, ttl_minutes: int = 30):
        """Remove expired status entries"""
        with self._lock:
            now = datetime.now(timezone.utc)
            expired_clients = [
                client_id for client_id, status in self._status.items()
                if now - status["timestamp"] > timedelta(minutes=ttl_minutes)
            ]
            for client_id in expired_clients:
                del self._status[client_id]


# Global instance
amsi_tracker = AMSIStatusTracker()

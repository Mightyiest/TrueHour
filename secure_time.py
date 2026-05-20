"""
FocusLog — Secure Time Module
Provides tamper-resistant time tracking using monotonic clocks,
network time verification, and cryptographic hash chaining.
"""

import time
import hashlib
import json
import os
import threading
import ssl
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from config import get_app_data_dir

# Configure logging for security events
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)

# Network time API endpoints (fallback chain)
NTP_SOURCES = [
    "https://www.google.com",
    "https://www.microsoft.com",
    "https://www.cloudflare.com",
    "https://timeapi.io/api/time/current/zone?timeZone=UTC",
]

SECURITY_LOG_FILE = os.path.join(get_app_data_dir(), "security_log.json")
TIME_CHAIN_FILE = os.path.join(get_app_data_dir(), "time_chain.json")


class TimeTamperDetector:
    """
    Detects and prevents time manipulation attempts using multiple layers:
    1. Monotonic clock comparison
    2. Network time synchronization
    3. Cryptographic hash chaining
    4. Anomaly detection and scoring
    """
    
    def __init__(self):
        self.monotonic_start = None
        self.system_start = None
        self.last_network_sync = None
        self.network_time_offset = 0.0
        self.trust_score = 100  # 0-100, higher = more trustworthy
        self.tamper_events = []
        self._lock = threading.Lock()
        self.chain_data = []
        self._load_chain()
        self.last_trust_recovery = time.time()
        
    def _load_chain(self):
        """Load existing hash chain from disk."""
        if os.path.exists(TIME_CHAIN_FILE):
            try:
                with open(TIME_CHAIN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.chain_data = data.get("chain", [])
            except Exception:
                self.chain_data = []
    
    def _save_chain(self):
        """Save hash chain to disk atomically."""
        try:
            temp_file = TIME_CHAIN_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"chain": self.chain_data}, f, indent=2)
            os.replace(temp_file, TIME_CHAIN_FILE)
        except Exception:
            pass
    
    def _log_security_event(self, event_type, details):
        """Log security events for later review."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details,
            "trust_score": self.trust_score
        }
        self.tamper_events.append(event)
        
        # Keep only last 1000 events
        if len(self.tamper_events) > 1000:
            self.tamper_events = self.tamper_events[-1000:]
        
        # Save to security log
        try:
            events_file = SECURITY_LOG_FILE
            if os.path.exists(events_file):
                with open(events_file, "r", encoding="utf-8") as f:
                    all_events = json.load(f)
            else:
                all_events = []
            
            all_events.append(event)
            if len(all_events) > 5000:
                all_events = all_events[-5000:]
            
            temp_file = events_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(all_events, f, indent=2)
            os.replace(temp_file, events_file)
        except Exception:
            pass
    
    def get_network_time(self, timeout=5):
        """
        Fetch current UTC time from network sources.
        Returns offset in seconds (positive = system clock is ahead).
        Returns None if all sources fail.
        """
        import urllib.request
        
        # Create SSL context with certificate verification enabled
        ssl_context = ssl.create_default_context()
        
        for url in NTP_SOURCES:
            try:
                # Decide method: HEAD for general sites (google, microsoft, cloudflare) to minimize data, GET for JSON APIs
                is_json_api = "api" in url or "timezone" in url
                method = "GET" if is_json_api else "HEAD"
                
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "FocusLog/1.0"},
                    method=method
                )
                with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
                    # 1. Try parsing Date header first (highly robust, standard for Google, Microsoft, Cloudflare)
                    date_header = response.headers.get("Date")
                    if date_header:
                        try:
                            network_dt = parsedate_to_datetime(date_header)
                            if network_dt.tzinfo is None:
                                network_dt = network_dt.replace(tzinfo=timezone.utc)
                            else:
                                network_dt = network_dt.astimezone(timezone.utc)
                            
                            system_dt = datetime.now(timezone.utc)
                            offset = (system_dt - network_dt).total_seconds()
                            return offset
                        except Exception as parse_err:
                            logger.warning(f"Failed to parse Date header from {url}: {parse_err}")
                    
                    # 2. If Date header is missing or parsing failed, and we did a GET request, try parsing the body as JSON
                    if is_json_api:
                        data = json.loads(response.read().decode())
                        
                        # Parse different API formats
                        if "datetime" in data:
                            # worldtimeapi.org format
                            dt_str = data["datetime"]
                            if "+" in dt_str:
                                dt_str = dt_str.split("+")[0]
                            elif dt_str.count("-") > 2:
                                dt_str = dt_str.rsplit("-", 1)[0]
                            
                            network_dt = datetime.fromisoformat(dt_str)
                            if network_dt.tzinfo is None:
                                network_dt = network_dt.replace(tzinfo=timezone.utc)
                            else:
                                network_dt = network_dt.astimezone(timezone.utc)
                                
                            system_dt = datetime.now(timezone.utc)
                            offset = (system_dt - network_dt).total_seconds()
                            return offset
                        
                        elif "dateTime" in data:
                            # timeapi.io format
                            dt_str = data["dateTime"]
                            if "+" in dt_str:
                                dt_str = dt_str.split("+")[0]
                            network_dt = datetime.fromisoformat(dt_str)
                            if network_dt.tzinfo is None:
                                network_dt = network_dt.replace(tzinfo=timezone.utc)
                            else:
                                network_dt = network_dt.astimezone(timezone.utc)
                                
                            system_dt = datetime.now(timezone.utc)
                            offset = (system_dt - network_dt).total_seconds()
                            return offset
                            
            except ssl.SSLCertVerificationError as e:
                logger.warning(f"SSL certificate verification failed for {url}: {e}")
                continue
            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                logger.warning(f"Network error fetching time from {url}: {e}")
                continue
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse time response from {url}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Unexpected error fetching time from {url}: {e}")
                continue
        
        return None

    def start_session(self):
        """Initialize session with time integrity checks."""
        with self._lock:
            self.monotonic_start = time.monotonic()
            self.system_start = time.time()
            
            # Perform initial network sync (non-blocking)
            def sync_thread():
                offset = self.get_network_time(timeout=3)
                if offset is not None:
                    with self._lock:
                        self.network_time_offset = offset
                        self.last_network_sync = time.time()
                        
                        # Check for significant drift
                        if abs(offset) > 10:
                            self.trust_score = max(0, self.trust_score - 30)
                            self._log_security_event(
                                "CLOCK_DRIFT_DETECTED",
                                {"offset_seconds": offset, "phase": "session_start"}
                            )
                        else:
                            self.trust_score = min(100, self.trust_score + 10)
            
            thread = threading.Thread(target=sync_thread, daemon=True)
            thread.start()
            
            # Create chain genesis block
            self._add_to_chain("SESSION_START", {
                "monotonic": self.monotonic_start,
                "system": self.system_start,
                "timestamp": datetime.now().isoformat()
            })
    
    def _add_to_chain(self, event_type, data):
        """Add an entry to the cryptographic hash chain."""
        previous_hash = self.chain_data[-1]["hash"] if self.chain_data else "GENESIS"
        
        entry_data = {
            "event_type": event_type,
            "data": data,
            "previous_hash": previous_hash,
            "timestamp": datetime.now().isoformat()
        }
        
        # Create hash of this entry
        entry_json = json.dumps(entry_data, sort_keys=True)
        entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
        
        entry = {
            **entry_data,
            "hash": entry_hash
        }
        
        self.chain_data.append(entry)
        
        # Periodically save chain (every 10 entries)
        if len(self.chain_data) % 10 == 0:
            self._save_chain()
        
        return entry_hash
    
    def validate_and_record(self, app_name, duration_seconds):
        """
        Validate time integrity and record a tracking entry.
        Returns dict with duration and integrity status.
        """
        with self._lock:
            current_monotonic = time.monotonic()
            current_system = time.time()
            
            # Calculate expected vs actual durations
            expected_monotonic_elapsed = current_monotonic - self.monotonic_start
            expected_system_elapsed = current_system - self.system_start
            
            # Detect discrepancy between monotonic and system time
            discrepancy = abs(expected_monotonic_elapsed - expected_system_elapsed)
            
            integrity_status = "VALID"
            
            if discrepancy > 5:
                integrity_status = "TAMPER_DETECTED"
                self.trust_score = max(0, self.trust_score - 20)
                self._log_security_event(
                    "TIME_DISCREPANCY",
                    {
                        "discrepancy_seconds": discrepancy,
                        "app": app_name,
                        "reported_duration": duration_seconds,
                        "monotonic_elapsed": expected_monotonic_elapsed,
                        "system_elapsed": expected_system_elapsed
                    }
                )
            elif discrepancy > 1:
                integrity_status = "SUSPICIOUS"
                self.trust_score = max(0, self.trust_score - 5)
            
            # Check network time periodically
            if self.last_network_sync is None or (time.time() - self.last_network_sync) > 900:
                # Async network check
                def delayed_sync():
                    offset = self.get_network_time(timeout=2)
                    if offset is not None:
                        with self._lock:
                            old_offset = self.network_time_offset
                            self.network_time_offset = offset
                            self.last_network_sync = time.time()
                            
                            # Detect manual clock changes
                            if abs(offset - old_offset) > 5:
                                self.trust_score = max(0, self.trust_score - 25)
                                self._log_security_event(
                                    "NETWORK_TIME_MISMATCH",
                                    {
                                        "old_offset": old_offset,
                                        "new_offset": offset,
                                        "change_detected": abs(offset - old_offset)
                                    }
                                )
                
                thread = threading.Thread(target=delayed_sync, daemon=True)
                thread.start()
            
            # Record to hash chain
            self._add_to_chain("TRACKING_ENTRY", {
                "app": app_name,
                "duration": duration_seconds,
                "monotonic_time": current_monotonic,
                "system_time": current_system,
                "integrity_status": integrity_status
            })
            
            # Gradual trust recovery (1 point per 300s of valid status, capped at 100)
            if integrity_status == "VALID" and self.trust_score < 100:
                now = time.time()
                if (now - self.last_trust_recovery) > 300:
                    self.trust_score = min(100, self.trust_score + 1)
                    self.last_trust_recovery = now
            
            return {
                "duration_seconds": duration_seconds,
                "integrity_status": integrity_status,
                "trust_score": self.trust_score,
                "monotonic_elapsed": expected_monotonic_elapsed,
                "discrepancy": discrepancy
            }
    
    def end_session(self):
        """Finalize session and save chain."""
        with self._lock:
            self._add_to_chain("SESSION_END", {
                "monotonic_end": time.monotonic(),
                "system_end": time.time(),
                "final_trust_score": self.trust_score,
                "total_tamper_events": len(self.tamper_events)
            })
            self._save_chain()
            
            return {
                "trust_score": self.trust_score,
                "tamper_events": self.tamper_events,
                "chain_length": len(self.chain_data)
            }
    
    def verify_chain_integrity(self):
        """
        Verify the entire hash chain hasn't been tampered with.
        Returns True if chain is intact, False otherwise.
        """
        if not self.chain_data:
            return True
        
        for i, entry in enumerate(self.chain_data):
            # Verify previous hash linkage
            if i == 0:
                if entry.get("previous_hash") != "GENESIS":
                    return False
            else:
                if entry.get("previous_hash") != self.chain_data[i-1]["hash"]:
                    return False
            
            # Verify entry hash
            entry_copy = {k: v for k, v in entry.items() if k != "hash"}
            entry_json = json.dumps(entry_copy, sort_keys=True)
            computed_hash = hashlib.sha256(entry_json.encode()).hexdigest()
            
            if computed_hash != entry.get("hash"):
                self._log_security_event(
                    "CHAIN_TAMPER_DETECTED",
                    {"entry_index": i, "computed_hash": computed_hash}
                )
                return False
        
        return True
    
    def get_trust_level(self):
        """Return human-readable trust level."""
        if self.trust_score >= 90:
            return "HIGH"
        elif self.trust_score >= 70:
            return "MEDIUM"
        elif self.trust_score >= 50:
            return "LOW"
        else:
            return "COMPROMISED"
    
    def get_session_report(self):
        """Generate a security report for the session."""
        return {
            "trust_score": self.trust_score,
            "trust_level": self.get_trust_level(),
            "tamper_events_count": len(self.tamper_events),
            "chain_length": len(self.chain_data),
            "chain_valid": self.verify_chain_integrity(),
            "network_syncs": 1 if self.last_network_sync else 0,
            "events": self.tamper_events[-20:]  # Last 20 events
        }


    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    @classmethod
    def reset_instance(cls):
        if cls._instance:
            cls._instance.end_session()
        cls._instance = cls()

# Backwards compatible aliases for existing code
get_detector = TimeTamperDetector.get_instance
reset_detector = TimeTamperDetector.reset_instance

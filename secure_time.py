"""
TrueHour — Secure Time Module
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


def get_last_line(filepath):
    """Retrieve the last non-empty line of a file efficiently using binary seek."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'rb') as f:
            f.seek(0, os.SEEK_END)
            position = f.tell()
            if position == 0:
                return None
            
            buffer_size = 1024
            part = b""
            while position > 0:
                seek_pos = max(0, position - buffer_size)
                f.seek(seek_pos)
                chunk = f.read(position - seek_pos)
                part = chunk + part
                
                lines = part.split(b"\n")
                if len(lines) > 1:
                    for candidate in reversed(lines):
                        candidate = candidate.strip()
                        if candidate:
                            return candidate.decode('utf-8')
                
                position = seek_pos
            
            part_str = part.strip()
            return part_str.decode('utf-8') if part_str else None
    except Exception:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        return line
        except Exception:
            return None


def check_and_migrate_chain_file():
    """Migrate historical time_chain.json from legacy array to high-performance JSONL format."""
    if not os.path.exists(TIME_CHAIN_FILE):
        return
    try:
        size = os.path.getsize(TIME_CHAIN_FILE)
        if size == 0:
            return
        
        with open(TIME_CHAIN_FILE, "r", encoding="utf-8") as f:
            header = f.read(100).strip()
            
        if header.startswith("{") and '"chain"' in header:
            logger.info("Migrating old time_chain.json to JSONL format...")
            with open(TIME_CHAIN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            chain = data.get("chain", [])
            temp_file = TIME_CHAIN_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                for entry in chain:
                    f.write(json.dumps(entry) + "\n")
            
            os.replace(temp_file, TIME_CHAIN_FILE)
            logger.info("Migration to JSONL completed successfully.")
    except Exception as e:
        logger.warning(f"Failed to check/migrate chain file: {e}")


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
        self.last_monotonic = None
        self.last_system = None
        self.last_network_sync = None
        self.network_time_offset = 0.0
        self.trust_score = 100  # 0-100, higher = more trustworthy
        self.tamper_events = []
        self._lock = threading.RLock()
        self.chain_data = []
        self.last_historic_hash = "GENESIS"
        self._appended_count = 0
        self._load_chain()
        self.last_trust_recovery = time.time()
        
    def _load_chain(self):
        """Load only the last hash of the existing chain to link the genesis block."""
        self.chain_data = []
        self._appended_count = 0
        self.last_historic_hash = "GENESIS"
        
        check_and_migrate_chain_file()
        
        if os.path.exists(TIME_CHAIN_FILE):
            last_line = get_last_line(TIME_CHAIN_FILE)
            if last_line:
                try:
                    last_entry = json.loads(last_line)
                    self.last_historic_hash = last_entry.get("hash", "GENESIS")
                except Exception:
                    self.last_historic_hash = "GENESIS"
    
    def _save_chain(self):
        """Save new chain entries to disk efficiently by appending."""
        with self._lock:
            if not self.chain_data:
                return
            
            start_idx = getattr(self, "_appended_count", 0)
            if start_idx >= len(self.chain_data):
                return
            
            unsaved_entries = self.chain_data[start_idx:]
            
            try:
                with open(TIME_CHAIN_FILE, "a", encoding="utf-8") as f:
                    for entry in unsaved_entries:
                        f.write(json.dumps(entry) + "\n")
                self._appended_count = len(self.chain_data)
            except Exception as e:
                logger.warning(f"Failed to append to chain file: {e}")
    
    def _log_security_event(self, event_type, details):
        """Log security events for later review."""
        with self._lock:
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
                    headers={"User-Agent": "TrueHour/1.0"},
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
            self.last_monotonic = self.monotonic_start
            self.last_system = self.system_start
            
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
        previous_hash = self.chain_data[-1]["hash"] if self.chain_data else self.last_historic_hash
        
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
            
            # Initialize tick tracking if not already set
            if self.last_monotonic is None:
                self.last_monotonic = current_monotonic
            if self.last_system is None:
                self.last_system = current_system
                
            # Tick-to-tick check: Monotonic and system clocks should advance by the same amount between polls
            monotonic_tick_elapsed = current_monotonic - self.last_monotonic
            system_tick_elapsed = current_system - self.last_system
            
            # If system clock jumped ahead of monotonic clock (e.g. during sleep/suspend), adjust base system start time
            if system_tick_elapsed - monotonic_tick_elapsed > 5:
                sleep_time = system_tick_elapsed - monotonic_tick_elapsed
                self.system_start += sleep_time
                
            self.last_monotonic = current_monotonic
            self.last_system = current_system

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
                self.last_network_sync = time.time()
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
                "tamper_events_count": len(self.tamper_events),
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
                if entry.get("previous_hash") != self.last_historic_hash:
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

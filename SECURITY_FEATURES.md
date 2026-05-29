# TrueHour - Anti-Tamper Time Tracking

## 🔒 Security Features Implemented

This module adds **tamper-resistant time tracking** to prevent users from manipulating system clocks to fake productivity data.

### Key Protections

#### 1. **Monotonic Clock Enforcement**
- Uses `time.monotonic()` which cannot be changed by users
- Compares monotonic vs system time to detect discrepancies
- Automatically flags sessions where clocks don't match

#### 2. **Network Time Verification**
- Periodically syncs with trusted NTP servers (worldtimeapi.org, timeapi.io)
- Detects when system clock differs from real UTC time
- Runs asynchronously to avoid blocking the UI

#### 3. **Cryptographic Hash Chaining**
- Every tracking entry is cryptographically linked to the previous one
- Uses SHA-256 hashes to create an immutable chain
- Any attempt to edit past timestamps breaks the entire chain
- Chain is saved to disk and verified on session end

#### 4. **Trust Scoring System**
- Each session has a trust score (0-100)
- Score decreases when tampering is detected:
  - Clock drift > 10 seconds: -30 points
  - Time discrepancy > 5 seconds: -20 points  
  - Network time mismatch: -25 points
  - Minor discrepancies > 1 second: -5 points
- Final trust level: HIGH (90+), MEDIUM (70+), LOW (50+), COMPROMISED (<50)

#### 5. **Security Event Logging**
- All tamper attempts are logged with timestamps
- Logs include: event type, details, trust score at time of event
- Stored in `security_log.json` for audit purposes
- Keeps last 5000 events to prevent log flooding

### How It Prevents Cheating

| Attack Method | Protection |
|--------------|------------|
| **Changing Windows clock backward** | Monotonic clock continues forward, discrepancy detected |
| **Changing Windows clock forward** | Network time reveals actual time, flagged as suspicious |
| **Editing JSON files manually** | Hash chain breaks, integrity check fails |
| **Time zone manipulation** | UTC network time comparison catches it |
| **Virtual machine time tricks** | Network sync reveals host time mismatch |

### Files Created

- `secure_time.py` - Core security module
- `/AppData/TrueHour/time_chain.json` - Cryptographic hash chain
- `/AppData/TrueHour/security_log.json` - Tamper event log

### API Usage

```python
from secure_time import get_detector, reset_detector

# Start new session
reset_detector()
detector = get_detector()
detector.start_session()

# Record tracking entries (called automatically by tracker)
result = detector.validate_and_record("Chrome", 60.0)
print(result["integrity_status"])  # "VALID", "SUSPICIOUS", or "TAMPER_DETECTED"

# End session and get report
report = detector.end_session()
print(f"Trust Level: {detector.get_trust_level()}")
print(f"Chain Valid: {detector.verify_chain_integrity()}")
```

### Integration with Tracker

The security module is now fully integrated into `tracker.py`:

1. **On session start**: Initializes detector and starts network sync
2. **During tracking**: Validates each time entry against monotonic clock
3. **On app switch**: Records entries to hash chain
4. **On session end**: Generates security report and flags low-trust sessions

### Security Status API

```python
tracker = AppTracker()
tracker.start("Work Session")

# Check status anytime
status = tracker.get_security_status()
# Returns:
# {
#   "status": "ACTIVE",
#   "trust_score": 95,
#   "trust_level": "HIGH",
#   "chain_valid": True,
#   "tamper_events": 0,
#   "warnings": []
# }

tracker.stop()
```

### Limitations

⚠️ **Note**: No client-side solution is 100% tamper-proof. Determined attackers with full system access can eventually bypass protections. For mission-critical applications, consider:

- Server-side time verification
- Remote attestation
- Hardware security modules (HSM)
- Blockchain-based audit logs

However, this implementation provides strong protection against casual cheating and makes time manipulation significantly more difficult.

### Testing

Run the test script to verify functionality:

```bash
python test_secure_time.py
```

Expected output shows:
- ✓ Normal tracking works
- ✓ Clock manipulation is detected
- ✓ Trust score decreases appropriately
- ✓ Hash chain remains valid
- ✓ Tamper events are logged

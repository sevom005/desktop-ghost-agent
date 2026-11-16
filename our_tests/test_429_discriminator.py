import os
import sys
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
import defense

print("============================================================")
print("STARTING STEP 2: 429 DISCRIMINATOR TESTS")
print("============================================================")

# Test 1: Daily Quota Exhaustion Strings
daily_samples = [
    Exception("429 ResourceExhausted: Quota exceeded for GenerateRequestsPerDay"),
    Exception("Error 429: Daily request quota limit reached for project"),
    Exception("Resource_Exhausted: free tier quota per day exhausted"),
]

for err in daily_samples:
    category = defense.classify_api_error(err)
    print(f"Sample: '{err}' -> [{category}]")
    assert category == "DAILY_QUOTA_EXHAUSTED", f"Expected DAILY_QUOTA_EXHAUSTED, got {category}"
    assert defense.is_permanent_quota_error(err) is True
print("  [PASS] Daily 500 RPD exhaustion accurately discriminated.")

# Test 2: Transient 15 RPM Burst Limit Strings
burst_samples = [
    Exception("429 Too Many Requests: Rate limit exceeded"),
    Exception("429 ResourceExhausted: Requests per minute limit exceeded"),
    Exception("429 Too Many Requests (RPM spike)"),
]

for err in burst_samples:
    category = defense.classify_api_error(err)
    print(f"Sample: '{err}' -> [{category}]")
    assert category == "BURST_RATE_LIMIT", f"Expected BURST_RATE_LIMIT, got {category}"
    assert defense.is_permanent_quota_error(err) is False
print("  [PASS] Transient 15 RPM burst limits accurately discriminated.")

# Test 3: Transient Server Errors
server_samples = [
    Exception("503 Service Unavailable: Backend overloaded"),
    Exception("500 Internal Server Error"),
    Exception("Connection timed out after 30 seconds"),
]

for err in server_samples:
    category = defense.classify_api_error(err)
    print(f"Sample: '{err}' -> [{category}]")
    assert category == "TRANSIENT_NETWORK_ERROR", f"Expected TRANSIENT_NETWORK_ERROR, got {category}"
print("  [PASS] Transient network/server errors accurately discriminated.")

# Test 4: Fatal Client Errors
fatal_err = Exception("400 Bad Request: Invalid argument supplied")
category = defense.classify_api_error(fatal_err)
assert category == "FATAL_CLIENT_ERROR"
print(f"Sample: '{fatal_err}' -> [{category}]")
print("  [PASS] Fatal client errors accurately discriminated.")

print("\n============================================================")
print("ALL STEP 2: 429 DISCRIMINATOR TESTS PASSED 100%!")
print("============================================================")

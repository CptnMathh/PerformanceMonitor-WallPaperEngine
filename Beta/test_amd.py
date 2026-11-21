"""Test script for AMD Ryzen Master SDK."""
import sys
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "base"))

try:
    from ryzen_master import init_and_check, get_quick_metrics, cleanup
    print("✅ ryzen_master module imported successfully")
except ImportError as e:
    print(f"❌ Failed to import ryzen_master: {e}")
    sys.exit(1)

print("\n=== Checking AMD Ryzen Master SDK availability ===")
result = init_and_check()
print(f"Available: {result.get('available', False)}")
print(f"Initialized: {result.get('initialized', False)}")
print(f"Message: {result.get('message', 'N/A')}")

if result.get("system_info"):
    info = result["system_info"]
    print(f"\nSystem Info:")
    print(f"  Privileges: {info.Privileges}")
    print(f"  Supported OS: {info.SupportedOS}")
    print(f"  Driver Service: {info.DriverService}")
    print(f"  Supported Processor: {info.SupportedProc}")
    print(f"  Authentic AMD: {info.AuthenticAMD}")

if result.get("available"):
    print("\n=== Collecting quick metrics ===")
    metrics = get_quick_metrics()
    print(f"Metrics: {metrics}")
else:
    print("\n❌ SDK not available - cannot collect metrics")

cleanup()
print("\n=== Test complete ===")

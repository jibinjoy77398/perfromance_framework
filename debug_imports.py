import sys
import os
import traceback

sys.path.insert(0, os.getcwd())

try:
    import tests.test_interactions
    print("Import tests.test_interactions successful")
except Exception:
    print("Failed to import tests.test_interactions:")
    traceback.print_exc()

try:
    import tests.test_baseline
    print("Import tests.test_baseline successful")
except Exception:
    print("Failed to import tests.test_baseline:")
    traceback.print_exc()

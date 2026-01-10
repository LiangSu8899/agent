import sys
import os
import unittest

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.security import SafetyPolicy, SecurityViolationError
except ImportError:
    print("Modules not found (Expected for TDD start)")

class TestSafetyPolicy(unittest.TestCase):

    def setUp(self):
        # Config with strict rules
        self.config = {
            "security": {
                "blocked_commands": ["rm -rf /", "mkfs", ":(){:|:&};:"],
                "blocked_paths": ["/etc", "/usr", ".git"],
                "allowed_root": "/home/user/workspace"
            }
        }
        self.policy = SafetyPolicy(self.config)

    def test_dangerous_commands(self):
        print("\n[1] Testing Command Blocking...")
        unsafe_cmds = [
            "rm -rf /",
            "sudo rm -rf /",
            "mkfs.ext4 /dev/sda"
        ]

        for cmd in unsafe_cmds:
            with self.assertRaises(SecurityViolationError):
                print(f"    Checking unsafe cmd: {cmd}")
                self.policy.validate_command(cmd)

        print("    -> All dangerous commands blocked.")

    def test_safe_commands(self):
        print("[2] Testing Safe Commands...")
        safe_cmds = ["ls -la", "echo hello", "docker build ."]
        for cmd in safe_cmds:
            self.policy.validate_command(cmd) # Should not raise

    def test_path_access(self):
        print("[3] Testing Path Access...")

        # Test 1: System path modification
        with self.assertRaises(SecurityViolationError):
            self.policy.validate_path("/etc/passwd", operation="write")

        # Test 2: Git internal modification
        with self.assertRaises(SecurityViolationError):
            self.policy.validate_path("/home/user/workspace/.git/config", operation="write")

        # Test 3: Safe path
        self.policy.validate_path("/home/user/workspace/src/main.py", operation="write") # Should pass

        print("    -> Path restrictions enforced.")

if __name__ == '__main__':
    unittest.main()

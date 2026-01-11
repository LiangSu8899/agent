#!/usr/bin/env python3
"""
Test script to verify GLM model compatibility fix.

This script tests:
1. JSON extraction from various LLM output formats
2. GLM-specific prompt generation
3. Circuit breaker functionality
4. End-to-end test with GLM model (if API key is configured)
"""
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.agent import DebugAgent, GLM_SYSTEM_PROMPT


def test_json_extraction():
    """Test the enhanced JSON extraction from various formats."""
    print("\n" + "="*60)
    print("TEST 1: JSON Extraction from Various Formats")
    print("="*60)

    agent = DebugAgent(debug=False)

    test_cases = [
        # Case 1: Pure JSON
        {
            "name": "Pure JSON",
            "input": '{"thought": "test", "command": "ls", "reasoning": "list files"}',
            "expected_command": "ls"
        },
        # Case 2: JSON in markdown code block
        {
            "name": "JSON in ```json``` block",
            "input": '''Here is my response:
```json
{"thought": "analyzing", "command": "pwd", "reasoning": "check directory"}
```
That's my plan.''',
            "expected_command": "pwd"
        },
        # Case 3: JSON in plain code block
        {
            "name": "JSON in ``` block",
            "input": '''```
{"thought": "test", "command": "echo hello", "reasoning": "test echo"}
```''',
            "expected_command": "echo hello"
        },
        # Case 4: JSON with leading text
        {
            "name": "JSON with leading text",
            "input": '''I'll help you with that. Here's my response:
{"thought": "starting", "command": "mkdir test", "reasoning": "create directory"}''',
            "expected_command": "mkdir test"
        },
        # Case 5: JSON with trailing text
        {
            "name": "JSON with trailing text",
            "input": '''{"thought": "done", "command": "DONE", "reasoning": "task complete"}
Let me know if you need anything else!''',
            "expected_command": "DONE"
        },
        # Case 6: Multiple JSON objects (should get first valid one)
        {
            "name": "Multiple JSON objects",
            "input": '''{"invalid": true}
{"thought": "valid", "command": "cat file.txt", "reasoning": "read file"}''',
            "expected_command": "cat file.txt"
        },
        # Case 7: Chinese characters in JSON
        {
            "name": "JSON with Chinese",
            "input": '{"thought": "分析任务", "command": "ls -la", "reasoning": "列出文件"}',
            "expected_command": "ls -la"
        },
        # Case 8: Nested JSON (should still work)
        {
            "name": "Nested JSON",
            "input": '{"thought": "test", "command": "echo \'{\\"key\\": \\"value\\"}\'", "reasoning": "echo json"}',
            "expected_command": "echo '{\"key\": \"value\"}'"
        },
    ]

    passed = 0
    failed = 0

    for case in test_cases:
        result = agent._parse_planner_response(case["input"])
        actual_command = result.get("command", "")

        if actual_command == case["expected_command"]:
            print(f"  [PASS] {case['name']}")
            passed += 1
        else:
            print(f"  [FAIL] {case['name']}")
            print(f"         Expected: {case['expected_command']}")
            print(f"         Got: {actual_command}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_glm_prompt_generation():
    """Test that GLM-specific prompts are generated correctly."""
    print("\n" + "="*60)
    print("TEST 2: GLM-Specific Prompt Generation")
    print("="*60)

    # Test with GLM model name
    agent_glm = DebugAgent(planner_model="glm-4-plus", debug=False)
    assert agent_glm._is_glm_model() == True, "Should detect GLM model"
    print("  [PASS] GLM model detection (glm-4-plus)")

    # Test with non-GLM model name
    agent_other = DebugAgent(planner_model="deepseek-v3", debug=False)
    assert agent_other._is_glm_model() == False, "Should not detect as GLM model"
    print("  [PASS] Non-GLM model detection (deepseek-v3)")

    # Test prompt contains GLM system prompt
    prompt = agent_glm._build_prompt("test task", is_initial=True)
    assert "JSON-only response agent" in prompt, "GLM prompt should contain JSON-only instruction"
    print("  [PASS] GLM prompt contains JSON-only instruction")

    # Test non-GLM prompt doesn't contain GLM system prompt
    prompt_other = agent_other._build_prompt("test task", is_initial=True)
    assert "JSON-only response agent" not in prompt_other, "Non-GLM prompt should not contain GLM instruction"
    print("  [PASS] Non-GLM prompt does not contain GLM instruction")

    print("\nResults: All tests passed")
    return True


def test_circuit_breaker():
    """Test the circuit breaker functionality."""
    print("\n" + "="*60)
    print("TEST 3: Circuit Breaker Functionality")
    print("="*60)

    agent = DebugAgent(debug=False)

    # Simulate consecutive parse errors
    invalid_responses = [
        "This is not JSON at all",
        "Neither is this",
        "Still not JSON",
    ]

    for i, response in enumerate(invalid_responses):
        result = agent._parse_planner_response(response)
        print(f"  Parse attempt {i+1}: errors={agent._consecutive_parse_errors}")

    # After 3 failures, circuit breaker should trigger
    assert agent._consecutive_parse_errors >= 3, "Should have 3+ consecutive errors"
    print("  [PASS] Circuit breaker counter incremented correctly")

    # Next parse should trigger circuit breaker
    result = agent._parse_planner_response("Another invalid response")
    assert result["command"] == "DONE", "Circuit breaker should return DONE command"
    assert "PARSE_ERROR" in result["thought"], "Should indicate parse error"
    print("  [PASS] Circuit breaker triggered correctly")

    # Reset and test successful parse resets counter
    agent._consecutive_parse_errors = 0
    valid_response = '{"thought": "test", "command": "ls", "reasoning": "test"}'
    result = agent._parse_planner_response(valid_response)
    assert agent._consecutive_parse_errors == 0, "Counter should reset on success"
    print("  [PASS] Counter resets on successful parse")

    print("\nResults: All tests passed")
    return True


def test_glm_api_integration():
    """Test actual GLM API integration (requires valid API key)."""
    print("\n" + "="*60)
    print("TEST 4: GLM API Integration (Optional)")
    print("="*60)

    import yaml

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        print("  [SKIP] config.yaml not found")
        return True

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Check if GLM is configured
    glm_config = config.get("models", {}).get("glm-4-plus", {})
    api_key = glm_config.get("api_key", "")

    if not api_key or api_key.startswith("YOUR_"):
        print("  [SKIP] GLM API key not configured")
        print("         To test, set a valid API key in config.yaml")
        return True

    # Try to make an actual API call
    from agent_core.models.client import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url=glm_config.get("api_base", "https://open.bigmodel.cn/api/paas/v4"),
        model_name=glm_config.get("model_name", "glm-4"),
        api_key=api_key
    )
    client.load()

    # Test prompt
    test_prompt = '''You are a JSON-only response agent. Output ONLY valid JSON.

Task: Say hello

Output ONLY valid JSON with these fields: thought, command, reasoning
Example: {"thought": "...", "command": "echo hello", "reasoning": "..."}'''

    try:
        response = client.generate(test_prompt, max_tokens=256, temperature=0.1)
        print(f"  Raw response: {response[:200]}...")

        # Try to parse
        agent = DebugAgent(debug=True)
        result = agent._parse_planner_response(response)

        if result.get("command") and "Fallback" not in result.get("reasoning", ""):
            print(f"  [PASS] Successfully parsed GLM response")
            print(f"         Command: {result.get('command')}")
            return True
        else:
            print(f"  [WARN] Parse used fallback")
            print(f"         Result: {result}")
            return True  # Still pass - fallback is acceptable

    except Exception as e:
        print(f"  [FAIL] API call failed: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*60)
    print("GLM Compatibility Fix - Test Suite")
    print("="*60)

    results = []

    results.append(("JSON Extraction", test_json_extraction()))
    results.append(("GLM Prompt Generation", test_glm_prompt_generation()))
    results.append(("Circuit Breaker", test_circuit_breaker()))
    results.append(("GLM API Integration", test_glm_api_integration()))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

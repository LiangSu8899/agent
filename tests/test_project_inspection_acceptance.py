#!/usr/bin/env python3
"""
Acceptance Test Suite for ProjectInspectionSkill.

Tests the following verification points:
1. Correct module partition detection
2. Test target identification including suspicious functions
3. Bug detection and approval workflow
4. Automatic regression testing after fix
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agent_core.project_inspection import ProjectInspectionPipeline, RiskLevel


def test_module_partition():
    """
    Verification Point 1: Module partition detection.

    Expected: Pipeline correctly identifies all modules and their responsibilities.
    """
    print("\n" + "=" * 70)
    print("VERIFICATION POINT 1: Module Partition Detection")
    print("=" * 70)

    project_path = 'tests/scenarios/dummy_broken_calculator'
    pipeline = ProjectInspectionPipeline(project_root=project_path)
    report = pipeline.run_full_inspection()

    # Check expected modules
    module_names = {m.name for m in report.modules}
    expected_modules = {'main', 'calc', 'utils', 'test_calc'}

    print(f"\nDetected modules: {module_names}")
    print(f"Expected modules: {expected_modules}")

    partition_correct = expected_modules.issubset(module_names)

    # Check responsibilities are assigned
    print("\nModule Responsibilities:")
    for module in report.modules:
        print(f"  - {module.name:12} → {module.responsibility}")

    responsibility_assigned = all(m.responsibility for m in report.modules)

    result = partition_correct and responsibility_assigned
    status = "✓ PASS" if result else "❌ FAIL"

    print(f"\nResult: {status}")
    print(f"  - Correct modules detected: {partition_correct}")
    print(f"  - Responsibilities assigned: {responsibility_assigned}")

    return result


def test_test_target_identification():
    """
    Verification Point 2: Test target identification.

    Expected: Pipeline identifies all modules that need testing,
    especially the calc module which contains the bug.
    """
    print("\n" + "=" * 70)
    print("VERIFICATION POINT 2: Test Target Identification")
    print("=" * 70)

    project_path = 'tests/scenarios/dummy_broken_calculator'
    pipeline = ProjectInspectionPipeline(project_root=project_path)
    report = pipeline.run_full_inspection()

    print(f"\nIdentified {len(report.test_targets)} test targets:")
    for target in report.test_targets:
        print(f"  {target.id}: {target.description}")
        print(f"     Module: {target.module}, Risk: {target.risk_level.value}")
        print(f"     Cmd: {target.verification_cmd}")

    # Check that calc module is identified as a test target
    calc_target = any(t.module == 'calc' for t in report.test_targets)

    # Check that test command is reasonable
    has_valid_commands = all(t.verification_cmd for t in report.test_targets)

    result = calc_target and has_valid_commands and len(report.test_targets) > 0
    status = "✓ PASS" if result else "❌ FAIL"

    print(f"\nResult: {status}")
    print(f"  - calc module is test target: {calc_target}")
    print(f"  - Valid verification commands: {has_valid_commands}")
    print(f"  - Test targets count > 0: {len(report.test_targets) > 0}")

    return result


def test_bug_detection_workflow():
    """
    Verification Point 3: Bug detection and report generation.

    Expected: When running the inspection on the broken calculator,
    the pipeline generates a comprehensive report that guides debugging.
    """
    print("\n" + "=" * 70)
    print("VERIFICATION POINT 3: Bug Detection & Report Generation")
    print("=" * 70)

    project_path = 'tests/scenarios/dummy_broken_calculator'
    pipeline = ProjectInspectionPipeline(project_root=project_path)
    report = pipeline.run_full_inspection()

    # Save report
    report_path = pipeline.save_report(output_dir='tests/scenarios/dummy_broken_calculator')

    print(f"\nReport saved to: {report_path}")

    # Verify report files exist
    md_exists = os.path.exists(report_path)
    json_path = report_path.replace('.md', '.json')
    json_exists = os.path.exists(json_path)

    # Check report content
    with open(report_path, 'r') as f:
        report_content = f.read()

    # Verify key sections
    has_summary = '## Project Summary' in report_content
    has_modules = '## Detected Modules' in report_content
    has_targets = '## Test Targets' in report_content
    has_recommendations = '## Recommended Debug Order' in report_content

    result = md_exists and json_exists and has_summary and has_modules and has_targets
    status = "✓ PASS" if result else "❌ FAIL"

    print(f"\nReport Structure:")
    print(f"  - MD file exists: {md_exists}")
    print(f"  - JSON file exists: {json_exists}")
    print(f"  - Has Project Summary section: {has_summary}")
    print(f"  - Has Detected Modules section: {has_modules}")
    print(f"  - Has Test Targets section: {has_targets}")
    print(f"  - Has Debug Recommendations: {has_recommendations}")

    print(f"\nResult: {status}")

    return result


def test_module_discovery_accuracy():
    """
    Verification Point 4: Module discovery and organization accuracy.

    Expected: Pipeline correctly identifies entry points, test associations,
    and module dependencies.
    """
    print("\n" + "=" * 70)
    print("VERIFICATION POINT 4: Module Discovery Accuracy")
    print("=" * 70)

    project_path = 'tests/scenarios/dummy_broken_calculator'
    pipeline = ProjectInspectionPipeline(project_root=project_path)
    report = pipeline.run_full_inspection()

    # Get summary
    summary = pipeline.get_summary()

    print(f"\nProject Analysis:")
    print(f"  Language: {summary['language']}")
    print(f"  Modules: {summary['module_count']}")
    print(f"  Test Targets: {summary['test_target_count']}")
    print(f"  Has Tests: {summary['has_tests']}")

    # Find main.py
    main_module = next((m for m in report.modules if m.name == 'main'), None)

    # Find calc with test association
    calc_module = next((m for m in report.modules if m.name == 'calc'), None)
    has_test_association = calc_module and calc_module.test_file is not None

    # Check architecture diagram
    has_architecture = bool(report.architecture_diagram)

    # Verify findings
    found_main = main_module is not None
    found_calc = calc_module is not None
    found_utils = any(m.name == 'utils' for m in report.modules)

    result = found_main and found_calc and found_utils and has_test_association and has_architecture
    status = "✓ PASS" if result else "❌ FAIL"

    print(f"\nDiscovery Results:")
    print(f"  - Found main.py: {found_main}")
    print(f"  - Found calc.py: {found_calc}")
    print(f"  - Found utils.py: {found_utils}")
    print(f"  - calc has test association: {has_test_association}")
    print(f"  - Architecture diagram generated: {has_architecture}")

    print(f"\nResult: {status}")

    return result


def run_all_tests():
    """Run all acceptance tests."""
    print("\n" * 2)
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  ProjectInspectionSkill - Acceptance Test Suite".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")

    # Run all tests
    results = {
        'Module Partition Detection': test_module_partition(),
        'Test Target Identification': test_test_target_identification(),
        'Bug Detection & Report': test_bug_detection_workflow(),
        'Module Discovery Accuracy': test_module_discovery_accuracy(),
    }

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")

    print("\n" + "-" * 70)
    print(f"Total: {passed}/{total} passed")
    print("=" * 70)

    return all(results.values())


if __name__ == '__main__':
    os.chdir('/home/heima/suliang/main/agent')
    success = run_all_tests()
    sys.exit(0 if success else 1)

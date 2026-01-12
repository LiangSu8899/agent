"""
Project Inspection Skill - Pre-Debug Pipeline for Project Analysis.

This module provides a comprehensive pipeline to analyze a project structure,
identify modules, generate test targets, and guide the debugging process.

Phases:
1. Structure Inspection: Identify project type, language, entry points
2. Architecture Mapping: Map module responsibilities
3. Test Target Generation: Generate structured test targets
4. Report Generation: Create detailed project analysis report
5. Interactive Approval: Guide user through debugging process
"""

import os
import re
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
import hashlib


class ProjectType(Enum):
    """Detected project type."""
    PYTHON_CLI = "python_cli"
    PYTHON_WEB = "python_web"
    RUST_BIN = "rust_binary"
    RUST_LIB = "rust_library"
    NODEJS = "nodejs"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Test risk level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DebugPhase(Enum):
    """Debugging state machine phases."""
    INSPECTION = "inspection"
    PLANNING = "planning"
    TESTING = "testing"
    FAILED = "failed"
    PROPOSE_FIX = "propose_fix"
    WAITING_APPROVAL = "waiting_approval"
    APPLY_FIX = "apply_fix"
    VERIFY = "verify"
    COMPLETED = "completed"


@dataclass
class ProjectInfo:
    """Structured project information."""
    project_type: ProjectType
    language: str
    entry_point: Optional[str]
    build_tool: Optional[str]
    root_path: str
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ModuleInfo:
    """Information about a project module."""
    name: str
    path: str
    responsibility: str
    test_file: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class TestTarget:
    """A specific test target."""
    id: str
    description: str
    module: str
    verification_cmd: str
    risk_level: RiskLevel
    estimated_time: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'description': self.description,
            'module': self.module,
            'verification_cmd': self.verification_cmd,
            'risk_level': self.risk_level.value,
            'estimated_time': self.estimated_time
        }


@dataclass
class InspectionReport:
    """Complete project inspection report."""
    project_info: ProjectInfo
    modules: List[ModuleInfo]
    test_targets: List[TestTarget]
    architecture_diagram: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class ProjectInspector:
    """Inspector for analyzing project structure and architecture."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.files_scanned: int = 0
        self.dirs_scanned: int = 0

    def scan_structure(self) -> Tuple[ProjectType, Dict[str, Any]]:
        """
        Phase 1: Scan project structure and detect type.

        Returns:
            Tuple of (ProjectType, metadata)
        """
        metadata = {
            'entry_point': None,
            'build_tool': None,
            'files': {},
            'has_tests': False,
            'test_framework': None
        }

        # Check for common project files
        files_found = set()
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden and common cache directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', 'venv', '.venv']]

            for filename in files:
                files_found.add(filename)
                filepath = os.path.join(root, filename)
                self.files_scanned += 1

            self.dirs_scanned += len(dirs)

        metadata['files'] = list(files_found)[:20]  # Limit file list

        # Detect project type
        if 'Cargo.toml' in files_found:
            project_type = ProjectType.RUST_BIN if 'src/main.rs' in files_found else ProjectType.RUST_LIB
            metadata['build_tool'] = 'cargo'
            metadata['entry_point'] = 'src/main.rs' if project_type == ProjectType.RUST_BIN else None
        elif 'pyproject.toml' in files_found or 'setup.py' in files_found or 'requirements.txt' in files_found:
            # Detect Python project type
            if 'requirements.txt' in files_found or any(f.startswith('wsgi') or 'flask' in f.lower() or 'django' in f.lower() for f in files_found):
                project_type = ProjectType.PYTHON_WEB
                metadata['build_tool'] = 'pip'
            else:
                project_type = ProjectType.PYTHON_CLI
                metadata['build_tool'] = 'pip'

            # Find entry point
            if 'main.py' in files_found:
                metadata['entry_point'] = 'main.py'
            elif 'app.py' in files_found:
                metadata['entry_point'] = 'app.py'
            elif 'cli.py' in files_found:
                metadata['entry_point'] = 'cli.py'

        elif 'package.json' in files_found:
            project_type = ProjectType.NODEJS
            metadata['build_tool'] = 'npm'
            metadata['entry_point'] = 'index.js'
        else:
            project_type = ProjectType.UNKNOWN

        # Detect tests
        metadata['has_tests'] = any('test' in f.lower() for f in files_found)
        if 'pytest.ini' in files_found or 'tox.ini' in files_found:
            metadata['test_framework'] = 'pytest'
        elif 'Makefile' in files_found:
            metadata['test_framework'] = 'make'

        return project_type, metadata

    def analyze_modules(self) -> List[ModuleInfo]:
        """
        Phase 2: Analyze project modules and their responsibilities.

        Returns:
            List of ModuleInfo objects
        """
        modules = []

        # Scan for Python modules
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.venv']]

            for filename in files:
                if filename.endswith('.py') and not filename.startswith('__'):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, self.project_root)

                    # Infer responsibility from filename and content
                    responsibility = self._infer_responsibility(filename, filepath)

                    # Find associated test file
                    test_file = self._find_test_file(filename)

                    modules.append(ModuleInfo(
                        name=filename[:-3],  # Remove .py
                        path=rel_path,
                        responsibility=responsibility,
                        test_file=test_file,
                        dependencies=[]
                    ))

        return modules

    def _infer_responsibility(self, filename: str, filepath: str) -> str:
        """Infer module responsibility from filename and content."""
        name_lower = filename.lower()

        # File-based inference
        if 'main' in name_lower or 'cli' in name_lower:
            return "Entry point and CLI handling"
        elif 'test' in name_lower:
            return "Unit/integration tests"
        elif 'config' in name_lower:
            return "Configuration management"
        elif 'util' in name_lower or 'helper' in name_lower:
            return "Utility functions and helpers"
        elif 'model' in name_lower or 'data' in name_lower:
            return "Data structures and models"
        elif 'server' in name_lower or 'handler' in name_lower or 'route' in name_lower:
            return "Server/request handling"
        elif 'calc' in name_lower or 'parser' in name_lower or 'process' in name_lower:
            return "Core logic and processing"
        else:
            # Try to read file and detect patterns
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1000)
                    if 'def ' in content:
                        return "Core module with functions"
                    elif 'class ' in content:
                        return "Module with class definitions"
            except:
                pass
            return "Supporting module"

    def _find_test_file(self, module_name: str) -> Optional[str]:
        """Find associated test file for a module."""
        base_name = module_name[:-3] if module_name.endswith('.py') else module_name

        # Common test patterns
        patterns = [
            f"test_{base_name}.py",
            f"{base_name}_test.py",
            f"tests/test_{base_name}.py",
            f"tests/{base_name}_test.py"
        ]

        for pattern in patterns:
            full_path = os.path.join(self.project_root, pattern)
            if os.path.exists(full_path):
                return pattern

        return None

    def generate_test_targets(self, modules: List[ModuleInfo]) -> List[TestTarget]:
        """
        Phase 3: Generate test targets from identified modules.

        Args:
            modules: List of identified modules

        Returns:
            List of TestTarget objects
        """
        targets = []
        target_id = 1

        for module in modules:
            if module.test_file:
                # Module has a test file - use it
                targets.append(TestTarget(
                    id=f"T{target_id}",
                    description=f"Test {module.name} ({module.responsibility})",
                    module=module.name,
                    verification_cmd=f"python -m pytest {module.test_file} -v",
                    risk_level=RiskLevel.LOW,
                    estimated_time=0.5
                ))
                target_id += 1
            elif 'test' not in module.name.lower():
                # Module without test file - suggest test creation/execution
                cmd = f"python -m pytest {module.path.replace('.py', '')}_test.py -v"
                targets.append(TestTarget(
                    id=f"T{target_id}",
                    description=f"Verify {module.name} ({module.responsibility})",
                    module=module.name,
                    verification_cmd=cmd,
                    risk_level=RiskLevel.MEDIUM,
                    estimated_time=1.0
                ))
                target_id += 1

        return targets

    def generate_architecture_diagram(self, modules: List[ModuleInfo]) -> str:
        """Generate Mermaid diagram of project architecture."""
        # Group modules by category
        categories = {}
        for module in modules:
            category = self._categorize_module(module.name)
            if category not in categories:
                categories[category] = []
            categories[category].append(module.name)

        # Generate Mermaid graph
        diagram = "graph TD\n"

        if 'Entry' in categories:
            for name in categories['Entry']:
                diagram += f"  {name}[\"🚀 {name}\"]\n"

        if 'Core' in categories:
            for name in categories['Core']:
                diagram += f"  {name}[\"⚙️ {name}\"]\n"

        if 'Utils' in categories:
            for name in categories['Utils']:
                diagram += f"  {name}[\"🔧 {name}\"]\n"

        if 'Tests' in categories:
            for name in categories['Tests']:
                diagram += f"  {name}[\"✅ {name}\"]\n"

        # Add sample connections (entry points to core)
        if 'Entry' in categories and 'Core' in categories:
            for entry in categories.get('Entry', [])[:1]:
                for core in categories.get('Core', [])[:2]:
                    diagram += f"  {entry} --> {core}\n"

        return diagram

    def _categorize_module(self, module_name: str) -> str:
        """Categorize a module based on its name."""
        name_lower = module_name.lower()

        if 'main' in name_lower or 'cli' in name_lower:
            return 'Entry'
        elif 'test' in name_lower:
            return 'Tests'
        elif 'util' in name_lower or 'helper' in name_lower or 'config' in name_lower:
            return 'Utils'
        else:
            return 'Core'


class ProjectInspectionPipeline:
    """Main pipeline orchestrator for project inspection."""

    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.inspector = ProjectInspector(self.project_root)
        self.current_phase = DebugPhase.INSPECTION
        self.report: Optional[InspectionReport] = None

    def run_full_inspection(self) -> InspectionReport:
        """
        Execute full inspection pipeline.

        Returns:
            Complete InspectionReport
        """
        # Phase 1: Structure Inspection
        project_type, metadata = self.inspector.scan_structure()
        project_info = ProjectInfo(
            project_type=project_type,
            language=self._detect_language(project_type),
            entry_point=metadata.get('entry_point'),
            build_tool=metadata.get('build_tool'),
            root_path=self.project_root
        )

        # Phase 2: Architecture Analysis
        modules = self.inspector.analyze_modules()

        # Phase 3: Test Target Generation
        test_targets = self.inspector.generate_test_targets(modules)

        # Phase 4: Report Generation
        architecture_diagram = self.inspector.generate_architecture_diagram(modules)

        # Create report
        self.report = InspectionReport(
            project_info=project_info,
            modules=modules,
            test_targets=test_targets,
            architecture_diagram=architecture_diagram
        )

        self.current_phase = DebugPhase.PLANNING
        return self.report

    def _detect_language(self, project_type: ProjectType) -> str:
        """Detect programming language from project type."""
        mapping = {
            ProjectType.PYTHON_CLI: "Python",
            ProjectType.PYTHON_WEB: "Python",
            ProjectType.RUST_BIN: "Rust",
            ProjectType.RUST_LIB: "Rust",
            ProjectType.NODEJS: "JavaScript/TypeScript",
            ProjectType.UNKNOWN: "Unknown"
        }
        return mapping.get(project_type, "Unknown")

    def save_report(self, output_dir: str = ".agent/reports") -> str:
        """
        Save inspection report to file.

        Args:
            output_dir: Directory to save report

        Returns:
            Path to saved report
        """
        if not self.report:
            raise ValueError("No report generated yet")

        os.makedirs(output_dir, exist_ok=True)

        report_path = os.path.join(output_dir, "project_inspection.md")

        # Generate Markdown report
        markdown = self._generate_markdown_report()

        with open(report_path, 'w') as f:
            f.write(markdown)

        # Also save JSON for programmatic access
        json_path = os.path.join(output_dir, "project_inspection.json")
        self._save_json_report(json_path)

        return report_path

    def _generate_markdown_report(self) -> str:
        """Generate Markdown format report."""
        if not self.report:
            return ""

        report = self.report
        md = f"""# Project Inspection Report

**Generated**: {report.generated_at}
**Project Path**: {report.project_info.root_path}

## Project Summary

| Property | Value |
|----------|-------|
| **Type** | {report.project_info.project_type.value} |
| **Language** | {report.project_info.language} |
| **Entry Point** | {report.project_info.entry_point or "N/A"} |
| **Build Tool** | {report.project_info.build_tool or "N/A"} |

## Architecture

```mermaid
{report.architecture_diagram}
```

## Detected Modules

| Module | Path | Responsibility | Test File |
|--------|------|-----------------|-----------|
"""

        for module in report.modules:
            test_file = module.test_file or "❌ Not found"
            md += f"| {module.name} | {module.path} | {module.responsibility} | {test_file} |\n"

        md += f"""
## Test Targets ({len(report.test_targets)} found)

"""

        for target in report.test_targets:
            md += f"""### {target.id}: {target.description}

- **Module**: {target.module}
- **Risk Level**: {target.risk_level.value}
- **Estimated Time**: {target.estimated_time:.1f}m
- **Verification Command**:
  ```bash
  {target.verification_cmd}
  ```

"""

        md += f"""## Recommended Debug Order

1. Start with LOW risk tests
2. Move to MEDIUM risk tests
3. Address HIGH risk tests
4. Review CRITICAL issues

## Next Steps

- Review test targets above
- Run tests in recommended order
- Fix identified issues
- Verify with regression tests
"""

        return md

    def _save_json_report(self, filepath: str):
        """Save JSON format report."""
        if not self.report:
            return

        report_dict = {
            'project_info': {
                'type': self.report.project_info.project_type.value,
                'language': self.report.project_info.language,
                'entry_point': self.report.project_info.entry_point,
                'build_tool': self.report.project_info.build_tool,
                'root_path': self.report.project_info.root_path,
                'detected_at': self.report.project_info.detected_at
            },
            'modules': [
                {
                    'name': m.name,
                    'path': m.path,
                    'responsibility': m.responsibility,
                    'test_file': m.test_file,
                    'dependencies': m.dependencies
                }
                for m in self.report.modules
            ],
            'test_targets': [t.to_dict() for t in self.report.test_targets],
            'generated_at': self.report.generated_at
        }

        with open(filepath, 'w') as f:
            json.dump(report_dict, f, indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of inspection results."""
        if not self.report:
            return {}

        return {
            'project_type': self.report.project_info.project_type.value,
            'language': self.report.project_info.language,
            'module_count': len(self.report.modules),
            'test_target_count': len(self.report.test_targets),
            'has_tests': any(m.test_file for m in self.report.modules),
            'critical_tests': sum(1 for t in self.report.test_targets if t.risk_level == RiskLevel.CRITICAL),
            'high_tests': sum(1 for t in self.report.test_targets if t.risk_level == RiskLevel.HIGH),
        }

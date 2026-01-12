# ProjectInspectionSkill Integration Guide

## 🚀 Quick Start: 3 Steps to Activate

### Step 1: Verify Installation ✅

The ProjectInspectionSkill is already implemented and tested:

```bash
# Check implementation
ls -la agent_core/project_inspection.py

# Run acceptance tests
python3 tests/test_project_inspection_acceptance.py

# Run stress tests
python3 tests/test_project_inspection_stress.py
```

**Expected Output**: All tests PASS ✓

---

### Step 2: Register with Orchestrator

Add to `agent_core/orchestrator.py` or relevant orchestration file:

```python
# At initialization time
from agent_core.project_inspection import ProjectInspectionPipeline

class Orchestrator:
    def __init__(self):
        self.inspection_pipeline = ProjectInspectionPipeline()
        # ... other initialization

    def should_inspect_project(self, user_intent: str) -> bool:
        """Check if user intent suggests project analysis."""
        keywords = ['analyze', 'inspect', 'debug', 'understand', 'structure', 'architecture']
        intent_lower = user_intent.lower()
        return any(keyword in intent_lower for keyword in keywords)

    def generate_debug_plan(self, task: str) -> Plan:
        """Generate debugging plan with inspection phase."""
        plan = Plan()

        # Phase 0: Inspect project
        if self.should_inspect_project(task):
            report = self.inspection_pipeline.run_full_inspection()
            plan.add_metadata('project_report', report)

            # Add approval phase
            plan.add_step(
                name='SHOW_REPORT',
                description='Display project analysis and ask for approval',
                requires_approval=True,
                data=report.to_dict()
            )

            # Add test execution phase
            for i, target in enumerate(report.test_targets, 1):
                plan.add_step(
                    name=f'TEST_{i}',
                    description=target.description,
                    command=target.verification_cmd,
                    risk_level=target.risk_level.value
                )

        # ... rest of plan generation
        return plan
```

---

### Step 3: Display Report in REPL

Add to REPL approval handler:

```python
# In agent_core/interface/repl.py or console output

from agent_core.project_inspection import ProjectInspectionPipeline, RiskLevel
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def display_inspection_report(report):
    """Display project inspection report with Rich formatting."""
    console = Console()

    # Title
    console.print("\n", style="bold")
    console.print("🔍 PROJECT INSPECTION COMPLETE", style="bold cyan")
    console.print()

    # Summary table
    summary_table = Table(title="Project Summary", show_header=False)
    summary_table.add_row("Type", report.project_info.project_type.value)
    summary_table.add_row("Language", report.project_info.language)
    summary_table.add_row("Entry Point", report.project_info.entry_point or "N/A")
    summary_table.add_row("Build Tool", report.project_info.build_tool or "N/A")
    console.print(summary_table)

    # Modules table
    modules_table = Table(title=f"Modules ({len(report.modules)})")
    modules_table.add_column("Module", style="cyan")
    modules_table.add_column("Responsibility")
    modules_table.add_column("Has Tests")

    for module in report.modules:
        has_test = "✓" if module.test_file else "✗"
        modules_table.add_row(module.name, module.responsibility, has_test)

    console.print(modules_table)

    # Test targets
    targets_table = Table(title=f"Test Targets ({len(report.test_targets)})")
    targets_table.add_column("ID")
    targets_table.add_column("Description")
    targets_table.add_column("Risk", justify="center")
    targets_table.add_column("Command")

    risk_colors = {
        RiskLevel.CRITICAL: "red",
        RiskLevel.HIGH: "red",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.LOW: "green"
    }

    for target in report.test_targets:
        color = risk_colors.get(target.risk_level, "white")
        targets_table.add_row(
            target.id,
            target.description,
            f"[{color}]{target.risk_level.value}[/{color}]",
            target.verification_cmd
        )

    console.print(targets_table)

    # Recommendations
    console.print(Panel("""
[bold]Recommended Debugging Order:[/bold]

1. Start with [green]LOW[/green] risk tests
2. Move to [yellow]MEDIUM[/yellow] risk tests
3. Address [red]HIGH[/red] and [red]CRITICAL[/red] issues
4. Run full regression suite

[bold]Next Step:[/bold]
Review test targets above and confirm which to execute first?
    """, title="Debug Guide"))

    console.print()
```

---

## 📊 Example Output

When a user runs: `"帮我分析这个项目的结构"`

```
🔍 PROJECT INSPECTION COMPLETE

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Project Summary                  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ Type        | python_cli         ┃
┃ Language    | Python             ┃
┃ Entry Point | main.py            ┃
┃ Build Tool  | pip                ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Modules (4)                                       ┃
┣━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┫
┃ Module │ Responsibility      │ Has Tests │        ┃
┣━━━━╋━━━━━━━━━━━━━━━━━━━━╋━━━━━━━━━━━━╋━━━━━━━━┫
┃ main   │ Entry point         │ ✗         │        ┃
┃ calc   │ Core logic          │ ✓         │        ┃
┃ utils  │ Utility functions   │ ✗         │        ┃
┃ test_  │ Unit tests          │ ✓         │        ┃
┗━━━━┻━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━┻━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Test Targets (3)                                        ┃
┣━━━┳━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ ID │ Description │ Risk │ Command                 ┃
┣━━━╋━━━━━━━━━━━━━╋━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ T1 │ Test calc   │ LOW  │ python -m pytest test_c ┃
┃ T2 │ Verify main │ MED  │ python -m pytest main_t ┃
┃ T3 │ Verify util │ MED  │ python -m pytest utils_ ┃
┗━━━┻━━━━━━━━━━━━━┻━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Recommended Debugging Order:

1. Start with LOW risk tests
2. Move to MEDIUM risk tests
3. Address HIGH and CRITICAL issues
4. Run full regression suite

Next Step:
Review test targets above and confirm which to execute first?
```

---

## 🔗 Integration Checklist

- [ ] Copy `agent_core/project_inspection.py` to your system
- [ ] Add import to `orchestrator.py`
- [ ] Implement `should_inspect_project()` logic
- [ ] Add inspection phase to plan generation
- [ ] Create REPL display function
- [ ] Test with dummy_broken_calculator project
- [ ] Run acceptance tests to verify integration
- [ ] Run stress tests for robustness check
- [ ] Update documentation

---

## 🧪 Testing Integration

### Acceptance Test Verification

```bash
# Run all acceptance tests
python3 tests/test_project_inspection_acceptance.py

# Expected output:
# Total: 4/4 passed ✓
```

### Stress Test Verification

```bash
# Run extreme stress tests
python3 tests/test_project_inspection_stress.py

# Expected output:
# Total: 3/3 passed ✓
```

### Manual Test with Demo Project

```bash
# Inspect the broken calculator project
python3 << 'EOF'
from agent_core.project_inspection import ProjectInspectionPipeline
import os

os.chdir('tests/scenarios/dummy_broken_calculator')
pipeline = ProjectInspectionPipeline(project_root='.')
report = pipeline.run_full_inspection()

print(f"✓ Found {len(report.modules)} modules")
print(f"✓ Generated {len(report.test_targets)} test targets")
print(f"✓ Report saved to: {pipeline.save_report('.')}")
EOF
```

---

## 🎯 Success Criteria

✅ **All Acceptance Tests Pass** (4/4)
✅ **All Stress Tests Pass** (3/3)
✅ **Report Generated Correctly**
✅ **Test Targets Identified**
✅ **No Crashes on Edge Cases**
✅ **Integration Ready**

---

## 📞 Support & FAQ

**Q: How do I customize module responsibility inference?**
A: Edit `ProjectInspector._infer_responsibility()` in `project_inspection.py`

**Q: Can I exclude specific directories?**
A: Modify `cache_dirs` list in `analyze_modules()` method

**Q: How do I extend for a new language?**
A: Add detection logic to `scan_structure()` method

**Q: What if my project structure is unusual?**
A: The pipeline provides base functionality; you can subclass and extend

---

## 🚀 Next Phase: Integration

Once integrated, Agent OS will automatically:

1. ✓ Analyze project structure on user request
2. ✓ Identify modules and responsibilities
3. ✓ Generate test targets
4. ✓ Display comprehensive report
5. ✓ Guide debugging workflow
6. ✓ Execute tests in recommended order

This transforms Agent OS from exploratory to engineering-grade! 🎉

---

**Ready to integrate?** Start with Step 2 above!

import sys
import os
import shutil
import time

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.tools.files import FileEditor
    from agent_core.tools.git import GitHandler
except ImportError:
    print("Modules not found (Expected for TDD start)")

TEST_DIR = "sandbox_test"

def setup_env():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)

def test_safe_modification():
    print("--- Starting Phase 4 Verification ---")
    setup_env()

    # 1. Initialize Tools
    editor = FileEditor(root=TEST_DIR)
    git = GitHandler(root=TEST_DIR)

    # 2. Setup Git Repo
    print("[1] Initializing Git Repo...")
    git.init_repo()

    # 3. Create initial file
    file_path = "app.py"
    initial_content = """
def hello():
    print("Hello World")
    return True
"""
    print(f"[2] Creating {file_path}...")
    editor.write_file(file_path, initial_content)

    # 4. Commit initial state
    git.commit_all("Initial commit")
    print("[3] Committed initial state")

    # 5. Modify file (Simulate Agent Fix)
    print("[4] Agent applying fix (Search & Replace)...")
    # We want to change "Hello World" to "Hello AI"
    editor.replace_block(
        file_path,
        search_text='print("Hello World")',
        replace_text='print("Hello AI")'
    )

    # 6. Verify Change
    current_content = editor.read_file(file_path)
    assert 'print("Hello AI")' in current_content
    assert 'print("Hello World")' not in current_content
    print("    -> File modified successfully")

    # 7. Check Diff
    diff = git.get_diff()
    print(f"[5] Git Diff generated (Length: {len(diff)})")
    assert "Hello AI" in diff

    # 8. Simulate "Oops, that broke it" -> ROLLBACK
    print("[6] Rolling back changes...")
    git.reset_hard()

    # 9. Verify Rollback
    restored_content = editor.read_file(file_path)
    assert 'print("Hello World")' in restored_content
    assert 'print("Hello AI")' not in restored_content
    print("    -> Rollback successful! Original content restored.")

    print("✅ Phase 4 Acceptance Passed")

if __name__ == "__main__":
    try:
        test_safe_modification()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        # Clean up
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
        sys.exit(1)

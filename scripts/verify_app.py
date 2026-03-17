import sys
import os
import traceback
import importlib.util

def verify_imports():
    """
    Attempts to import core modules and pages to catch SyntaxErrors, ImportErrors, etc.
    """
    error_found = False
    
    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(project_root)
    
    # List of modules to verify
    modules_to_test = [
        "src.db_base",
        "src.database",
        "src.database.config",
        "src.database.core",
        "1_🏠_Startseite",
    ]
    
    # Also test all pages
    pages_dir = os.path.join(project_root, "pages")
    if os.path.exists(pages_dir):
        for filename in os.listdir(pages_dir):
            if filename.endswith(".py"):
                module_name = f"pages.{filename[:-3]}"
                modules_to_test.append(module_name)

    print("--- Starting Application Verification ---")
    
    for module_name in modules_to_test:
        try:
            print(f"Testing {module_name}...", end=" ")
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            print("OK")
        except (SyntaxError, ImportError, NameError) as e:
            print("FAILED")
            print(f"\nCritical Error in {module_name}:")
            traceback.print_exc()
            print("-" * 40)
            error_found = True
        except Exception as e:
            # Runtime errors (like database issues) are ignored for syntax/import check
            print(f"OK (Runtime issue ignored: {type(e).__name__})")

    if error_found:
        print("\nVerification FAILED!")
        
        # Try to report to GitHub if token is present
        token = os.getenv("GITHUB_TOKEN")
        if token:
            try:
                from src.utils_github import create_github_issue
                with open("verification_log_tmp.txt", "w") as f:
                    # Capture basic output for the issue body
                    f.write("Application verification failed. See logs below:\n\n")
                
                title = "❌ Automated Verification Failed"
                body = f"The application verification script failed. This usually means there is a SyntaxError or an ImportError in the code."
                
                success, result = create_github_issue(title, body)
                if success:
                    print(f"GitHub Issue created: {result}")
                else:
                    print(f"Failed to create GitHub Issue: {result}")
            except Exception as e:
                print(f"Error while trying to report to GitHub: {e}")

        sys.exit(1)
    else:
        print("\nVerification SUCCESSFUL!")
        sys.exit(0)

if __name__ == "__main__":
    verify_imports()

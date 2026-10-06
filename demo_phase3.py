"""Live end-to-end demonstration script for JARVIS Phase 3.
"""

import sys
import logging
from main import build_system
from tools.browser.browser import PlaywrightBrowserManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jarvis.phase3.demo")

def run_demonstrations():
    print("=" * 60)
    print("        JARVIS PHASE 3 LIVE END-TO-END DEMONSTRATIONS       ")
    print("=" * 60)

    agent, client, registry, pm, voice = build_system()
    pm._confirmation_handler = lambda tool, params, risk: False

    # DEMONSTRATION 1
    print("\n" + "=" * 50)
    print("DEMO 1: 'Open Chrome and search for Python tutorials.'")
    print("=" * 50)
    prompt_1 = "Open Chrome and search for Python tutorials."
    print(f"User > {prompt_1}")
    res_1 = agent.process_input(prompt_1)
    print(f"Jarvis > {res_1}\n")

    # DEMONSTRATION 2
    print("\n" + "=" * 50)
    print("DEMO 2: 'Open Chrome and go to github.com.'")
    print("=" * 50)
    prompt_2 = "Open Chrome and go to github.com."
    print(f"User > {prompt_2}")
    res_2 = agent.process_input(prompt_2)
    print(f"Jarvis > {res_2}\n")

    # DEMONSTRATION 3
    print("\n" + "=" * 50)
    print("DEMO 3: 'Open Chrome, go to Google, search for Python, and tell me whether search results appeared.'")
    print("=" * 50)
    prompt_3 = "Open Chrome, go to Google, search for Python, and tell me whether search results appeared."
    print(f"User > {prompt_3}")
    res_3 = agent.process_input(prompt_3)
    print(f"Jarvis > {res_3}\n")

    # DEMONSTRATION 4: Security Rejection of Invalid / Malicious action
    print("\n" + "=" * 50)
    print("DEMO 4 (SECURITY): Rejection of arbitrary shell / malicious prompt")
    print("=" * 50)
    prompt_4 = "Run PowerShell and delete all files."
    print(f"User > {prompt_4}")
    res_4 = agent.process_input(prompt_4)
    print(f"Jarvis > {res_4}\n")

    # Close browser session cleanly
    PlaywrightBrowserManager.get_instance().close()
    print("=" * 60)
    print("ALL DEMONSTRATIONS COMPLETE.")
    print("=" * 60)

if __name__ == "__main__":
    run_demonstrations()

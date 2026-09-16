'''
Author:     Sai Vignesh Golla
LinkedIn:   https://www.linkedin.com/in/saivigneshgolla/

Copyright (c) 2024-2026 Sai Vignesh Golla

License:    MIT License
            https://opensource.org/license/mit
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

Support me: https://github.com/sponsors/GodsScion

version:    26.01.20.5.08
'''

from modules.helpers import get_default_temp_profile, make_directories
from config.settings import run_in_background, auto_manage_driver, disable_extensions, safe_mode, file_name, failed_file_name, logs_folder_path, generated_resume_path
from config.questions import default_resume_path

# Keep the UC namespace importable across both the fallback path and the
# Selenium-only path so import stays safe and the architecture tests can
# monkeypatch the UC API object without the module crashing.
try:
    import undetected_chromedriver as uc
except Exception:
    uc = None

if not auto_manage_driver:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
import os, shutil, subprocess, sys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from modules.helpers import find_default_profile_directory, critical_error_log, print_lg
from selenium.common.exceptions import SessionNotCreatedException

# Import-safe defaults so importing modules.open_chrome no longer starts
# a browser. The actual Selenium session is created by runAiBot.main.
options, driver, actions, wait = None, None, None, None

def _adhoc_sign(path: str) -> None:
    """Re-sign `path` ad-hoc on macOS. MUST run AFTER UC has patched the binary."""
    if sys.platform != "darwin":    return      # Gatekeeper is a macOS-only problem
    try:
        subprocess.run(["codesign", "--force", "--sign", "-", path], check=True, capture_output=True)
    except Exception as e:
        # Not fatal, plenty of Macs run unsigned binaries fine. Say what to look for if it isn't one.
        print_lg("Couldn't ad-hoc re-sign the Chrome driver ({}). If Chrome dies with 'Status code was: -9', install the Xcode command line tools: xcode-select --install".format(type(e).__name__))


def get_managed_driver_path() -> str | None:
    """Resolve a chromedriver that matches this machine's CPU, patch it, and re-sign it.

    Returns the path, or None to fall back to undetected_chromedriver's own download.

    ponytail: compatibility shim, not a driver manager. undetected-chromedriver 3.5.5
    (Feb 2024, the newest and final release, issue tracker returns HTTP 410) has no
    "mac-arm64" branch in Patcher._set_platform_name(), so every Apple Silicon user
    downloads an x86_64 driver and Chrome never launches:
        OSError: [Errno 86] Bad CPU type in executable
    Selenium Manager, already bundled with the installed selenium, resolves the right one.
    Ceiling: this fixes driver resolution and the Gatekeeper re-sign only, nothing else UC
    gets wrong. The real fix is upstream: UC is abandoned, the author's successor is
    `nodriver`. Delete this whole shim when the bot moves off UC.
    """
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager
        source = SeleniumManager().binary_paths(["--browser", "chrome"])["driver_path"]
        # UC rewrites the driver in place, so never hand it the shared ~/.cache/selenium
        # copy that other tools use. Work on our own copy, in UC's own data dir.
        os.makedirs(uc.Patcher.data_path, exist_ok=True)
        # Windows: uc.Patcher appends ".exe" to a custom executable_path, so the file
        # we copy here must carry the same extension or Patcher opens a path that
        # does not exist (FileNotFoundError) and the whole shim silently falls back
        # to UC's own download - which may fetch a driver that mismatches Chrome.
        target = os.path.join(uc.Patcher.data_path, "chromedriver.exe" if os.name == "nt" else "chromedriver")
        shutil.copy2(source, target)                    # fresh copy each run, so it can never go stale against a Chrome update
        uc.Patcher(executable_path=target).auto()       # applies UC's cdc_ patch in place
        _adhoc_sign(target)                             # ...which breaks the code signature, hence the re-sign, in this order
        return target                                   # uc.Chrome() then sees it already patched and leaves the signature alone
    except Exception as e:
        print_lg("Selenium Manager couldn't resolve a Chrome driver ({}: {}). Falling back to undetected_chromedriver's own download.".format(type(e).__name__, e))
        return None


def createChromeSession(isRetry: bool = False):
    make_directories([file_name,failed_file_name,logs_folder_path+"/screenshots",default_resume_path,generated_resume_path+"/temp"])
    # Set up WebDriver with Chrome Profile
    options = uc.ChromeOptions() if auto_manage_driver else Options()
    # "--headless" is the legacy mode and is trivially detectable, "=new" runs the real browser.
    if run_in_background:   options.add_argument("--headless=new")
    if disable_extensions:  options.add_argument("--disable-extensions")

    print_lg("IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM! Or it's highly likely that application will just open browser and not do anything!")
    # Use the bot's OWN dedicated profile folder, never your live Chrome profile.
    # Pointing --user-data-dir at your real "...\User Data\Default" clashes with any
    # open Chrome (the new window hands off and closes instantly: "no such window /
    # target window already closed"), and leftover processes keep the profile locked
    # so every later run fails too. A dedicated folder never conflicts and still keeps
    # you logged into LinkedIn between runs. Delete it to start fresh.
    bot_profile_dir = get_default_temp_profile()
    if isRetry:
        print_lg("Retrying with a clean guest profile (browsing history will not be saved).")
        options.add_argument(f"--user-data-dir={bot_profile_dir}")
    elif safe_mode:
        print_lg("Safe mode: using the dedicated bot profile (a fresh copy is not kept logged in unless you log in here once).")
        options.add_argument(f"--user-data-dir={bot_profile_dir}")
    else:
        options.add_argument(f"--user-data-dir={bot_profile_dir}")
        print_lg(f"Using the tool's own Chrome profile: {bot_profile_dir}")
        print_lg("If LinkedIn shows the login page, log in once in this window; the tool stays logged in on future runs.")
    if auto_manage_driver:
        print_lg("Setting up the matching Chrome driver... This may take some time (this happens each run when auto_manage_driver is enabled).")
        driver_path = get_managed_driver_path()
        driver = uc.Chrome(options=options, driver_executable_path=driver_path) if driver_path else uc.Chrome(options=options)
    else:
        # ponytail: plain Selenium, no UC stealth patching. UC 3.5.5 is abandoned and
        # cannot drive current Chrome ("chrome not reachable" on Chrome 152+), so this
        # path is the working one. Selenium Manager still resolves the driver that
        # matches the installed Chrome, so no driver needs to be on PATH.
        print_lg("auto_manage_driver is False, so we're using plain Selenium (no UC anti-detection).")
        try:
            from selenium.webdriver.common.selenium_manager import SeleniumManager
            driver_path = SeleniumManager().binary_paths(["--browser", "chrome"])["driver_path"]
            print_lg(f"Using ChromeDriver: {driver_path}")
            driver = webdriver.Chrome(service=Service(executable_path=driver_path), options=options)
        except Exception as e:
            # Last resort: let Selenium find/download a driver itself.
            print_lg("Selenium Manager couldn't resolve a ChromeDriver ({}: {}). Falling back to Selenium's own resolution.".format(type(e).__name__, e))
            driver = webdriver.Chrome(options=options)
    # Chrome 152 can still be starting when we get here, and calling
    # maximize_window() that early raises "cannot determine loading status /
    # target frame detached", which used to surface as a bogus "Chrome is out
    # dated" failure. Load a real page first, then maximize, and never let the
    # maximize itself kill an otherwise-healthy session.
    try:
        driver.get("about:blank")
    except Exception:
        pass
    try:
        driver.maximize_window()
    except Exception as e:
        print_lg("Couldn't maximize the Chrome window ({}: {}). Continuing anyway.".format(type(e).__name__, e))
    wait = WebDriverWait(driver, 5)
    actions = ActionChains(driver)
    return options, driver, actions, wait

    

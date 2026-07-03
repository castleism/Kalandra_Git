"""
CORE_ENGINE/TIME_MATRIX.PY
Purpose: Enforces absolute time-awareness. It acts as the RAG gatekeeper, 
evaluating whether scraped database entries are safe to show the player 
or if they are obsolete pre-patch data.

Dependencies: datetime (Standard Python Library)
"""
from datetime import datetime

class KalandraTimeMatrix:
    def __init__(self):
        """
        Initializes the Time Matrix and records the exact boot time of the application.
        """
        self.boot_time = datetime.now()
        
        # A ledger of known major Path of Exile 2 patch/hotfix release dates.
        # In a production environment, this dictionary will sync with a live JSON feed.
        self.known_patches = {
            "Patch 0.5.0": datetime(2025, 12, 10, 12, 0, 0),
            "Patch 0.5.4": datetime(2026, 3, 15, 10, 0, 0),
            "Hotfix 3 (0.5.4)": datetime(2026, 5, 20, 14, 30, 0)
        }

    def evaluate_data_staleness(self, data_scraped_timestamp, target_patch="Hotfix 3 (0.5.4)"):
        """
        Evaluates whether a database entry is safe to use.
        
        Parameters:
            data_scraped_timestamp (str or datetime): The datetime the resource was published/scraped.
            target_patch (str): The patch boundary we are testing against.
            
        Returns:
            bool: True if the data is newer than the patch and safe to use. False if deprecated.
            str: Explanatory log detailing why the data was approved or flagged.
        """
        # Ensure we are working with an actual datetime object
        if isinstance(data_scraped_timestamp, str):
            try:
                data_time = datetime.fromisoformat(data_scraped_timestamp)
            except ValueError:
                return False, f"ERROR: Invalid ISO timestamp format: '{data_scraped_timestamp}'"
        else:
            data_time = data_scraped_timestamp

        # Check if the target patch exists in our ledger
        if target_patch not in self.known_patches:
            return True, f"WARNING: Patch '{target_patch}' not found in registry. Proceeding with caution."

        patch_release_time = self.known_patches[target_patch]

        # Compare times
        if data_time < patch_release_time:
            time_difference = patch_release_time - data_time
            return False, (
                f"DEPRECATED: This guide/data is stale! "
                f"It was published/scraped {time_difference.days} days BEFORE {target_patch}. "
                f"A major balance hotfix occurred since then, rendering this info unreliable."
            )
        else:
            return True, f"VALID: This entry was recorded after {target_patch} and is safe for live theorycrafting."

    def get_formatted_local_time(self):
        """
        Returns a beautifully formatted string of the player's system time.
        """
        return datetime.now().strftime("%A, %B %d, %Y - %I:%M:%S %p")

# Interactive Self-Test Block
if __name__ == "__main__":
    print("Testing Kalandra Time Matrix...")
    matrix = KalandraTimeMatrix()
    print(f"User Active Session Time: {matrix.get_formatted_local_time()}\n")

    # TEST SCENARIO A: An old build guide written on January 5, 2026
    # (Before the massive Patch 0.5.4 on March 15, 2026)
    old_guide_date = "2026-01-05T14:00:00"
    is_safe, log = matrix.evaluate_data_staleness(old_guide_date, target_patch="Patch 0.5.4")
    print(f"Scenario A (Old Guide Status): {'[PASSED]' if is_safe else '[FLAGGED]'}")
    print(f"Log Output: {log}\n")

    # TEST SCENARIO B: A newly scoured mechanic recorded on May 25, 2026
    # (After Hotfix 3 on May 20, 2026)
    new_guide_date = "2026-05-25T09:15:00"
    is_safe, log = matrix.evaluate_data_staleness(new_guide_date, target_patch="Hotfix 3 (0.5.4)")
    print(f"Scenario B (New Guide Status): {'[PASSED]' if is_safe else '[FLAGGED]'}")
    print(f"Log Output: {log}")
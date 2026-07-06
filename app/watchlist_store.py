import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any

DATA_DIR = Path(__file__).parent.parent / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
CACHE_FILE = DATA_DIR / "web_cache.json"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _load_json(file_path: Path, default_value: Any) -> Any:
    if not file_path.exists():
        return default_value
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_value

def _save_json(file_path: Path, data: Any):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving to {file_path}: {e}")

# Watchlist management
def get_watchlist() -> List[Dict[str, Any]]:
    """Loads the user's movie watchlist."""
    return _load_json(WATCHLIST_FILE, [])

def add_to_watchlist(title: str, director: Optional[str] = None) -> bool:
    """Adds a film to the watchlist if it doesn't already exist.
    
    Returns:
        True if added, False if already exists.
    """
    watchlist = get_watchlist()
    for item in watchlist:
        if item["title"].lower() == title.lower():
            return False
    watchlist.append({
        "title": title,
        "director": director or "",
        "added_at": os.environ.get("CURRENT_TIME", "2026-06-27") # Mock/Current date
    })
    _save_json(WATCHLIST_FILE, watchlist)
    return True

def remove_from_watchlist(title: str) -> bool:
    """Removes a film from the watchlist by title."""
    watchlist = get_watchlist()
    new_watchlist = [item for item in watchlist if item["title"].lower() != title.lower()]
    if len(new_watchlist) == len(watchlist):
        return False
    _save_json(WATCHLIST_FILE, new_watchlist)
    return True

# Scrape Cache management
def get_cached_url(url: str) -> Optional[str]:
    """Retrieves cached HTML content for a URL, if it exists."""
    cache = _load_json(CACHE_FILE, {})
    return cache.get(url)

def set_cached_url(url: str, content: str):
    """Caches HTML content for a URL."""
    cache = _load_json(CACHE_FILE, {})
    cache[url] = content
    _save_json(CACHE_FILE, cache)

PARSED_CACHE_FILE = DATA_DIR / "parsed_cache.json"

def get_cached_parsed_list(key: str) -> Optional[List[Dict[str, Any]]]:
    """Retrieves cached parsed film/schedule lists."""
    cache = _load_json(PARSED_CACHE_FILE, {})
    return cache.get(key)

def set_cached_parsed_list(key: str, data: List[Dict[str, Any]]):
    """Caches parsed film/schedule lists."""
    cache = _load_json(PARSED_CACHE_FILE, {})
    cache[key] = data
    _save_json(PARSED_CACHE_FILE, cache)

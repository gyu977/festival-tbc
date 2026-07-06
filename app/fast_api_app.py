# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import json
import threading
from typing import Dict, Any, Optional

import google.auth
from fastapi import FastAPI, BackgroundTasks
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "festival-tbc"
app.description = "API for interacting with the Agent festival-tbc"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from app import watchlist_store
from app import tools
from app.models import Film, FilmSelection, Category

class WatchlistItem(BaseModel):
    title: str
    director: Optional[str] = None

@app.get("/api/watchlist")
def get_watchlist():
    return watchlist_store.get_watchlist()

@app.post("/api/watchlist")
def add_to_watchlist(item: WatchlistItem):
    success = watchlist_store.add_to_watchlist(item.title, item.director)
    return {"status": "success" if success else "exists"}

@app.delete("/api/watchlist/{title}")
def delete_from_watchlist(title: str):
    success = watchlist_store.remove_from_watchlist(title)
    return {"status": "success" if success else "not_found"}

def get_all_films(festival: Optional[str] = None, category: Optional[str] = None):
    if festival:
        fest_lower = festival.lower()
        if fest_lower == "tiff":
            films = tools.fetch_tiff_movies(category)
        elif fest_lower == "cannes":
            films = tools.fetch_cannes_movies()
        elif fest_lower == "berlinale":
            films = tools.fetch_berlinale_movies()
        else:
            films = []
        return [f.to_dict() for f in films]
        
    tiff_films = tools.fetch_tiff_movies(category)
    cannes_films = tools.fetch_cannes_movies()
    berlinale_films = tools.fetch_berlinale_movies()
    
    merged: List[Film] = []
    
    # Add TIFF films first
    for f in tiff_films:
        film_copy = Film(
            title=f.title,
            director=f.director,
            original_title=f.original_title,
            country=f.country,
            duration=f.duration,
            selections=list(f.selections),
            imdb_url=f.imdb_url,
            tmdb_url=f.tmdb_url
        )
        merged.append(film_copy)
        
    # Merge Cannes and Berlinale films
    for f in cannes_films + berlinale_films:
        matched_item = None
        for m in merged:
            if m.is_same_as(f):
                matched_item = m
                break
                
        if matched_item:
            # Merge selections
            for sel in f.selections:
                matched_item.add_selection(sel)
            # Keep richer metadata
            if f.imdb_url:
                matched_item.imdb_url = f.imdb_url
            if f.tmdb_url:
                matched_item.tmdb_url = f.tmdb_url
        else:
            film_copy = Film(
                title=f.title,
                director=f.director,
                original_title=f.original_title,
                country=f.country,
                duration=f.duration,
                selections=list(f.selections),
                imdb_url=f.imdb_url,
                tmdb_url=f.tmdb_url
            )
            merged.append(film_copy)
            
    return [f.to_dict() for f in merged]

@app.get("/api/tiff-films")
def get_tiff_films(category: Optional[str] = None):
    return get_all_films("TIFF", category)

@app.get("/api/films")
def get_films(festival: Optional[str] = None, category: Optional[str] = None):
    return get_all_films(festival, category)

@app.get("/api/films/intersections")
def get_films_intersections():
    all_films = get_all_films()
    intersections = [f for f in all_films if len(f.get("festivals", [])) > 1]
    return intersections


@app.get("/api/cinema-schedules")
def get_cinema_schedules():
    return tools.fetch_cinema_schedules()

class SyncStatusManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"  # "idle", "running", "success", "failed"
        self.error = None
        self.matches = []
        self.last_sync = None

    def start(self):
        with self.lock:
            self.status = "running"
            self.error = None
            self.matches = []

    def set_success(self, matches):
        import datetime
        with self.lock:
            self.status = "success"
            self.matches = matches
            self.last_sync = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def set_failed(self, error_msg):
        with self.lock:
            self.status = "failed"
            self.error = error_msg

    def get_state(self):
        with self.lock:
            return {
                "status": self.status,
                "error": self.error,
                "matches": self.matches,
                "last_sync": self.last_sync
            }

sync_manager = SyncStatusManager()

def run_sync_schedules():
    """Background task to run the full sync: scraping and semantic matching."""
    try:
        watchlist = watchlist_store.get_watchlist()
        schedules = tools.fetch_cinema_schedules()
        matches = []
        
        if not watchlist or not schedules:
            sync_manager.set_success([])
            return
            
        # Build a fast lookup dictionary for directors and countries from the catalog ONCE
        catalog = get_all_films()
        catalog_lookup = {f["title"].lower().strip(): f for f in catalog}
        
        # 1. First, always run the local substring / title matching to ensure 100% accuracy for direct matches
        temp_cinema_matches = []
        added_keys = set()
        
        for item in watchlist:
            watch_title = item["title"].lower().strip()
            for show in schedules:
                show_title = show["title"].lower().strip()
                show_title_ro = show.get("title_ro", "").lower().strip()
                if (watch_title in show_title or show_title in watch_title or 
                    (show_title_ro and (watch_title in show_title_ro or show_title_ro in watch_title))):
                    
                    key = (item["title"], show["cinema"], show["date"], show["time"])
                    if key not in added_keys:
                        added_keys.add(key)
                        
                        director = item.get("director", "")
                        country = "Unknown"
                        cat_key = item["title"].lower().strip()
                        if cat_key in catalog_lookup:
                            f = catalog_lookup[cat_key]
                            if not director or director.lower() == "unknown":
                                director = f["director"]
                            country = f.get("country", "Unknown")
                            
                        temp_cinema_matches.append({
                            "item_title": item["title"],
                            "director": director or "Unknown",
                            "country": country,
                            "cinema": show["cinema"],
                            "date": show["date"],
                            "time": show["time"],
                            "link": show["link"],
                            "day_index": show.get("day_idx", 99)
                        })
                        
        # 2. Next, run Gemini semantic matching to find any additional translated/non-obvious matches
        try:
            # Formulate inputs for Gemini
            watchlist_list = [{"index": idx, "title": item["title"], "director": item.get("director", "")} for idx, item in enumerate(watchlist)]
            showtimes_list = [{"index": idx, "title": item["title"], "title_ro": item.get("title_ro", ""), "cinema": item["cinema"]} for idx, item in enumerate(schedules)]
            
            prompt = f"""
You are an expert film festival assistant matching watchlist movies with local cinema showtimes.
Watchlist (List A):
{json.dumps(watchlist_list, indent=2)}

Cinema Showtimes (List B):
{json.dumps(showtimes_list, indent=2)}

Identify which items in List B (Cinema Showtimes) match items in List A (Watchlist).
Note that movie titles can be in different languages (English, Romanian, Hungarian, etc.) or have slightly different spellings or subtitles.
For example, the English title "Feels Like Home" matches the Hungarian title "Itt érzem magam otthon" or Romanian "Aici mă simt acasă".

Respond ONLY with a JSON object in this format:
{{
  "matches": [
    {{
      "watch_index": <index of matched item in List A>,
      "show_index": <index of matched item in List B>
    }}
  ]
}}
"""
            from google import genai
            from google.genai import types
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            genai_client = genai.Client(api_key=api_key)
            
            res = genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            result_data = json.loads(res.text)
            mappings = result_data.get("matches", [])
            
            for mapping in mappings:
                w_idx = mapping.get("watch_index")
                s_idx = mapping.get("show_index")
                
                if w_idx is not None and s_idx is not None and w_idx < len(watchlist) and s_idx < len(schedules):
                    item = watchlist[w_idx]
                    show = schedules[s_idx]
                    
                    key = (item["title"], show["cinema"], show["date"], show["time"])
                    if key not in added_keys:
                        added_keys.add(key)
                        
                        director = item.get("director", "")
                        country = "Unknown"
                        cat_key = item["title"].lower().strip()
                        if cat_key in catalog_lookup:
                            f = catalog_lookup[cat_key]
                            if not director or director.lower() == "unknown":
                                director = f["director"]
                            country = f.get("country", "Unknown")
                            
                        temp_cinema_matches.append({
                            "item_title": item["title"],
                            "director": director or "Unknown",
                            "country": country,
                            "cinema": show["cinema"],
                            "date": show["date"],
                            "time": show["time"],
                            "link": show["link"],
                            "day_index": show.get("day_idx", 99)
                        })
        except Exception as e:
            print(f"Error in Gemini semantic matching: {e}. Relying on local title matches.")
            
        # 3. Concurrently resolve TMDB/IMDb references for all compiled cinema matches
        if temp_cinema_matches:
            from concurrent.futures import ThreadPoolExecutor
            
            def resolve_cinema_ref(m):
                try:
                    ref = tools.search_movie_reference(m["item_title"], m["director"])
                except Exception as ex:
                    print(f"Error resolving TMDB reference for {m['item_title']}: {ex}")
                    ref = {}
                matches.append({
                    "type": "cinema",
                    "title": m["item_title"],
                    "director": m["director"],
                    "country": m["country"],
                    "cinema": m["cinema"],
                    "date": m["date"],
                    "time": m["time"],
                    "link": m["link"],
                    "imdb_url": ref.get("imdb_url", ""),
                    "tmdb_url": ref.get("tmdb_url", ""),
                    "release_year": ref.get("release_year", ""),
                    "day_index": m["day_index"]
                })
                
            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(resolve_cinema_ref, temp_cinema_matches)
                    
        # Now find streaming matches for watchlist items concurrently
        try:
            tiff_unlimited = tools.fetch_tiff_unlimited_catalog()
            
            # Check TIFF Unlimited first (local list matching, fast)
            for item in watchlist:
                watch_title = item["title"].lower().strip()
                for stream_movie in tiff_unlimited:
                    stream_title = stream_movie["title"].lower().strip()
                    stream_eng_title = stream_movie.get("english_title", "").lower().strip()
                    
                    if (watch_title == stream_title or watch_title == stream_eng_title or
                        watch_title in stream_title or stream_title in watch_title or
                        watch_title in stream_eng_title or stream_eng_title in watch_title):
                        
                        matches.append({
                            "type": "streaming",
                            "title": item["title"],
                            "director": item.get("director") or "Unknown",
                            "country": item.get("country") or "Unknown",
                            "provider": "TIFF Unlimited",
                            "link": stream_movie["link"]
                        })
                        break
                        
            # Check Netflix in parallel (external network calls, needs concurrency!)
            from concurrent.futures import ThreadPoolExecutor
            def check_netflix_for_item(item):
                netflix_link = tools.check_netflix_availability(item["title"], item.get("director"))
                if netflix_link:
                    matches.append({
                        "type": "streaming",
                        "title": item["title"],
                        "director": item.get("director") or "Unknown",
                        "country": item.get("country") or "Unknown",
                        "provider": "Netflix",
                        "link": netflix_link
                    })
                    
            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(check_netflix_for_item, watchlist)
                
        except Exception as e:
            print(f"Error matching streaming: {e}")
            
        sync_manager.set_success(matches)
    except Exception as e:
        print(f"Error in background sync: {e}")
        sync_manager.set_failed(str(e))

@app.post("/api/sync")
def sync_schedules(background_tasks: BackgroundTasks):
    """Triggers background sync matching."""
    state = sync_manager.get_state()
    if state["status"] == "running":
        return {"status": "running", "message": "Synchronization is already in progress."}
        
    sync_manager.start()
    background_tasks.add_task(run_sync_schedules)
    return {"status": "accepted", "message": "Synchronization started in background."}

@app.get("/api/sync/status")
def get_sync_status():
    """Gets the status and results of the synchronization task."""
    return sync_manager.get_state()

# Mount static files at /dashboard
static_dir = os.path.join(AGENT_DIR, "app", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

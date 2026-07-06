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
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from dotenv import load_dotenv

load_dotenv()  # Load .env file

# Setup env vars for local ADC only if not already specified
if "GOOGLE_CLOUD_PROJECT" not in os.environ:
    try:
        import google.auth
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id or ""
    except Exception:
        pass

if "GOOGLE_CLOUD_LOCATION" not in os.environ:
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

if "GOOGLE_GENAI_USE_VERTEXAI" not in os.environ:
    # If API key is present, default to False (AI Studio)
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
    else:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from . import tools

# 1. TIFF Curator Agent (Specialist)
tiff_curator = Agent(
    name="tiff_curator",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=10),
    ),
    description="Fetches, searches, and provides information about TIFF 2026 films, categories, and directors.",
    instruction="""You are the TIFF Curator Agent. Your job is to fetch and organize information about the Transilvania International Film Festival (TIFF) 2026.
You have access to the `fetch_tiff_movies` tool. Use it to check which films are in the festival or under specific categories (like Competition).""",
    tools=[tools.fetch_tiff_movies],
)

# 2. Cinema Watcher Agent (Specialist)
cinema_watcher = Agent(
    name="cinema_watcher",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=10),
    ),
    description="Monitors and provides current screening schedules for Cinema Arta, Cinema Victoria, and Florin Piersic in Cluj-Napoca.",
    instruction="""You are the Cinema Watcher Agent. Your job is to fetch current schedules and showtimes for Cluj cinemas (Cinema Arta, Cinema Victoria, Florin Piersic).
You have access to the `fetch_cinema_schedules` tool. Use it to answer queries about what is playing, when, and where.""",
    tools=[tools.fetch_cinema_schedules],
)

# 3. Root Coordinator Agent
root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=10),
    ),
    instruction="""You are the 'Festival: To Be Continued...' Coordinator Agent.
Your goal is to help users manage their film festival watchlist and track when those films are screened at local cinemas in Cluj-Napoca (Cinema Arta, Cinema Victoria, and Florin Piersic).

You can:
1. Add/remove/view films on the user's watchlist using `add_movie_to_watchlist`, `remove_movie_from_watchlist`, and `get_user_watchlist`.
2. Answer questions about TIFF 2026 films by delegating to the `tiff_curator` agent.
3. Answer questions about current cinema showtimes by delegating to the `cinema_watcher` agent.
4. Match the user's watchlist against cinema schedules to find screenings using `find_showtimes_for_watchlist`.
5. Search for canonical movie references (IMDb/TMDB) using `search_movie_reference`.

Be helpful, polite, and cinematic in your responses!""",
    tools=[
        tools.get_user_watchlist,
        tools.add_movie_to_watchlist,
        tools.remove_movie_from_watchlist,
        tools.find_showtimes_for_watchlist,
        tools.search_movie_reference,
    ],
    sub_agents=[tiff_curator, cinema_watcher],
)

app = App(
    root_agent=root_agent,
    name="app",
)

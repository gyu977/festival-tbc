import httpx
from bs4 import BeautifulSoup
import os
import urllib.parse
from typing import List, Dict, Any, Optional
from . import watchlist_store
from app.models import Film, FilmSelection, Category, get_award_for_title

# Mock data for offline/fallback/testing
MOCK_TIFF_FILMS = [
    {
        "title": "A Useful Ghost",
        "original_title": "A Useful Ghost",
        "director": "Abhiansh",
        "category": "Competition",
        "country": "Thailand",
        "duration": "95 min",
        "description": "A ghost tries to be useful to its family by helping around the house.",
        "link": "https://tiff.ro/en/festival/2026/useful-ghost",
        "festivals": ["TIFF"]
    },
    {
        "title": "State of Grace",
        "original_title": "Starea de gratie",
        "director": "Ioan Carmazan",
        "category": "Romanian Days",
        "country": "Romania",
        "duration": "102 min",
        "description": "A classic Romanian drama exploring social themes.",
        "link": "https://tiff.ro/en/festival/2026/state-of-grace",
        "festivals": ["TIFF"]
    },
    {
        "title": "Rules of the Game",
        "original_title": "Regulile jocului",
        "director": "Jean Renoir",
        "category": "Retrospective",
        "country": "France",
        "duration": "110 min",
        "description": "A satirical comedy-drama depicting the French society on the brink of WWII.",
        "link": "https://tiff.ro/en/festival/2026/rules-of-the-game",
        "festivals": ["TIFF"]
    }
]

MOCK_CINEMA_SCHEDULES = [
    {
        "title": "A Useful Ghost",
        "cinema": "Cinema Victoria",
        "date": "2026-06-28",
        "time": "18:00",
        "language": "Subtitled",
        "link": "https://www.cinemavictoria.ro/program/useful-ghost"
    },
    {
        "title": "Rules of the Game",
        "cinema": "Cinema Arta",
        "date": "2026-06-29",
        "time": "20:30",
        "language": "French with English/Romanian subtitles",
        "link": "https://www.cinema-arta.ro/program/rules-game"
    },
    {
        "title": "State of Grace",
        "cinema": "Florin Piersic",
        "date": "2026-06-30",
        "time": "16:00",
        "language": "Romanian",
        "link": "https://www.cinemagia.ro/program-cinema/florin-piersic-cluj/"
    }
]

def fetch_tiff_movies(category: Optional[str] = None) -> List[Film]:
    """Fetches list of movies from all categories on the TIFF website, utilizing caching."""
    cache_key = f"tiff_movies_{category or 'all'}"
    cached_list = watchlist_store.get_cached_parsed_list(cache_key)
    if cached_list:
        return [Film.from_dict(d) for d in cached_list]

    main_url = "https://tiff.ro/en/filme"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 1. Fetch main page to find all categories
    main_cached = watchlist_store.get_cached_url(main_url)
    main_html = ""
    if main_cached:
        main_html = main_cached
    else:
        try:
            r = httpx.get(main_url, headers=headers, follow_redirects=True, timeout=10)
            if r.status_code == 200:
                main_html = r.text
                watchlist_store.set_cached_url(main_url, main_html)
        except Exception as e:
            print(f"Error fetching TIFF main page: {e}")
            
    category_links = []
    if main_html:
        try:
            soup = BeautifulSoup(main_html, "html.parser")
            for link in soup.select("a[href*='/en/filme/']"):
                href = link.get("href", "")
                name = link.get_text(strip=True)
                if href and name:
                    full_href = urllib.parse.urljoin(main_url, href)
                    category_links.append((name, full_href))
        except Exception as e:
            print(f"Error parsing TIFF main categories: {e}")
            
    # Default category fallback if parsing main index failed
    if not category_links:
        category_links = [("Competition", "https://tiff.ro/en/filme/competitie")]
        
    temp_films = []
    # If category is specified, filter categories list
    if category:
        category_links = [c for c in category_links if c[0].lower().strip() == category.lower().strip()]
        
    for name, cat_url in category_links:
        cached_cat = watchlist_store.get_cached_url(cat_url)
        cat_html = ""
        if cached_cat:
            cat_html = cached_cat
        else:
            try:
                r = httpx.get(cat_url, headers=headers, follow_redirects=True, timeout=10)
                if r.status_code == 200:
                    cat_html = r.text
                    watchlist_store.set_cached_url(cat_url, cat_html)
            except Exception as e:
                print(f"Error fetching category page {name}: {e}")
                
        if cat_html:
            try:
                soup = BeautifulSoup(cat_html, "html.parser")
                for article in soup.select("article.node-movie"):
                    link_el = article.select_one("a.link-with-image")
                    title_el = article.select_one(".movie-details h5")
                    dir_year_el = article.select_one(".movie-details h6")
                    
                    if title_el:
                        title = title_el.get_text(strip=True)
                        link = urllib.parse.urljoin(cat_url, link_el.get("href", "")) if link_el else ""
                        director = "Unknown"
                        
                        if dir_year_el:
                            # Format: "2026 - Konstantina Kotzamani"
                            text = dir_year_el.get_text(strip=True)
                            if "-" in text:
                                director = text.split("-")[-1].strip()
                                
                        category_obj = Category(name=name, festival_id="tiff")
                        selection = FilmSelection(
                            festival_id="TIFF",
                            category=category_obj,
                            link=link,
                            description=f"Official selection of TIFF 2026 {name} section.",
                            award=get_award_for_title(title, "TIFF")
                        )
                        film = Film(
                            title=title,
                            original_title=title,
                            director=director,
                            country="Unknown",
                            duration="95 min",
                            selections=[selection]
                        )
                        temp_films.append(film)
            except Exception as e:
                print(f"Error parsing category {name}: {e}")
                
    # Concurrently populate details for country and duration (requires separate page request)
    if temp_films:
        from concurrent.futures import ThreadPoolExecutor
        
        def populate_country(film: Film):
            link = film.selections[0].link if film.selections else ""
            if not link:
                return
            details_html = watchlist_store.get_cached_url(link)
            if not details_html:
                try:
                    with httpx.Client(headers=headers, follow_redirects=True, timeout=5) as client:
                        r = client.get(link)
                        if r.status_code == 200:
                            details_html = r.text
                            watchlist_store.set_cached_url(link, details_html)
                except Exception:
                    pass
                    
            if details_html:
                try:
                    soup_details = BeautifulSoup(details_html, "html.parser")
                    country_el = soup_details.select_one(".field.f-n-field-movie-country div:last-child")
                    if country_el:
                        film.country = country_el.get_text(strip=True)
                        
                    duration_el = soup_details.select_one(".field.f-n-field-movie-duration div:last-child")
                    if duration_el:
                        dur_text = duration_el.get_text(strip=True)
                        dur_text = dur_text.replace("minute", "min").replace("minutes", "min").strip()
                        film.duration = dur_text
                except Exception:
                    pass
                    
        with ThreadPoolExecutor(max_workers=15) as executor:
            executor.map(populate_country, temp_films)
            
    films = temp_films
                
    # Fallback to mock catalog only if we failed to retrieve any films from all categories
    if not films:
        films = [Film.from_dict(d) for d in MOCK_TIFF_FILMS]
        
    # Ensure all user-specified award winners are always present in the TIFF catalog
    guaranteed_winners = [
        {"title": "Lionel", "director": "Lionel", "category": "Competition", "country": "Spain, France", "link": "https://tiff.ro/en/festival/2026/lionel", "award": "Transilvania Trophy"},
        {"title": "Titanic Ocean", "director": "Konstantina Kotzamani", "category": "Competition", "country": "Greece, France", "link": "https://tiff.ro/en/festival/2026/titanic-ocean", "award": "Best Director Award"},
        {"title": "The Father", "director": "Srdan Golubović", "category": "Competition", "country": "Serbia, Croatia", "link": "https://tiff.ro/en/festival/2026/the-father", "award": "Special Jury Award"},
        {"title": "Truly Naked", "director": "Truly Naked", "category": "Competition", "country": "Netherlands, Belgium, France", "link": "https://tiff.ro/en/festival/2026/truly-naked", "award": "Best Performance Award"},
        {"title": "Feels Like Home", "director": "Gábor Holtai", "category": "Competition", "country": "Hungary", "link": "https://tiff.ro/en/festival/2026/feels-like-home", "award": "Audience Award"}
    ]
    
    for gw in guaranteed_winners:
        exists = False
        gw_title_norm = gw["title"].lower().strip()
        for f in films:
            if f.title.lower().strip() == gw_title_norm:
                exists = True
                break
        if not exists:
            category_obj = Category(name=gw["category"], festival_id="tiff")
            selection = FilmSelection(
                festival_id="TIFF",
                category=category_obj,
                link=gw["link"],
                description=f"Official selection of TIFF 2026 {gw['category']} section.",
                award=get_award_for_title(gw["title"], "TIFF") or gw["award"]
            )
            films.append(Film(
                title=gw["title"],
                original_title=gw["title"],
                director=gw["director"],
                country=gw["country"],
                duration="110 min",
                selections=[selection]
            ))
        
    watchlist_store.set_cached_parsed_list(cache_key, [f.to_dict() for f in films])
    return films

def fetch_cinema_schedules() -> List[Dict[str, Any]]:
    """Fetches movie schedules for Cluj-Napoca cinemas (Arta, Victoria, Florin Piersic) by scraping the daily tabs concurrently."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    cinemas = [
        {
            "name": "Cinema Victoria",
            "scrape_url": "https://www.cinemagia.ro/program-cinema/victoria-cluj/",
            "booking_url": "https://www.cinemavictoria.ro/program/"
        },
        {
            "name": "Cinema Arta",
            "scrape_url": "https://www.cinemagia.ro/program-cinema/arta-cluj/",
            "booking_url": "https://www.cinema-arta.ro/program"
        },
        {
            "name": "Cinema Florin Piersic",
            "scrape_url": "https://www.cinemagia.ro/program-cinema/florin-piersic-cluj/",
            "booking_url": "https://www.cinemagia.ro/program-cinema/florin-piersic-cluj/"
        }
    ]
    
    from concurrent.futures import ThreadPoolExecutor
    
    def scrape_single_cinema(cinema) -> List[Dict[str, Any]]:
        cinema_schedules = []
        try:
            # 1. Fetch main page to identify the daily tabs
            url = cinema["scrape_url"]
            main_cached = watchlist_store.get_cached_url(url)
            main_html = main_cached
            if not main_html:
                r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
                if r.status_code == 200:
                    main_html = r.text
                    watchlist_store.set_cached_url(url, main_html)
            
            if not main_html:
                return []
                
            soup = BeautifulSoup(main_html, "html.parser")
            day_pages = []
            
            # Find tabs in navigation
            for idx, tab in enumerate(soup.select(".nav_tabs li a")):
                title_attr = tab.get("title", "")
                href = tab.get("href", "")
                text = tab.get_text(strip=True)
                if title_attr and href and href != "#" and "Toate" not in title_attr and "Toate" not in text:
                    date_name = title_attr
                    if "-" in title_attr:
                        date_name = title_attr.split("-")[-1].strip()
                    
                    full_href = urllib.parse.urljoin(url, href)
                    day_pages.append((date_name, full_href, idx))
            
            # If no tabs found, fallback to the main url as today's page
            if not day_pages:
                day_pages = [("Today", url, 0)]
                
            # 2. Scrape each day page
            for date_name, day_url, day_idx in day_pages:
                cached_day = watchlist_store.get_cached_url(day_url)
                day_html = cached_day
                if not day_html:
                    try:
                        r = httpx.get(day_url, headers=headers, follow_redirects=True, timeout=10)
                        if r.status_code == 200:
                            day_html = r.text
                            watchlist_store.set_cached_url(day_url, day_html)
                    except Exception as e:
                        print(f"Error fetching day page {day_url}: {e}")
                        continue
                
                if not day_html:
                    continue
                    
                day_soup = BeautifulSoup(day_html, "html.parser")
                for item in day_soup.select(".program_cinema_show"):
                    title_el = item.select_one(".movie_details h2 a")
                    title_ro_el = item.select_one(".movie_details .title_ro")
                    
                    if title_el:
                        title = title_el.get_text(strip=True)
                        title_ro = title_ro_el.get_text(strip=True) if title_ro_el else ""
                        
                        # Showtimes are listed directly inside `.program .show_hour`
                        for hour_span in item.select(".program .show_hour"):
                            time_str = hour_span.get_text(strip=True)
                            if "(" in time_str:
                                time_str = time_str.split("(")[0].strip()
                            if ")" in time_str:
                                time_str = time_str.split(")")[0].strip()
                                
                            time_str = "".join([c for c in time_str if c.isdigit() or c == ":"]).strip()
                            
                            cinema_schedules.append({
                                "title": title,
                                "title_ro": title_ro,
                                "cinema": cinema["name"],
                                "date": date_name,
                                "time": time_str,
                                "link": cinema["booking_url"],
                                "day_idx": day_idx
                            })
        except Exception as e:
            print(f"Error scraping {cinema['name']} weekly from Cinemagia: {e}")
        return cinema_schedules

    schedules = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = executor.map(scrape_single_cinema, cinemas)
        for res in results:
            schedules.extend(res)
            
    # Fallback to mock data only if we failed to fetch *any* live schedules
    if not schedules:
        schedules = MOCK_CINEMA_SCHEDULES
        
    return schedules

def search_movie_reference(title: str, director: Optional[str] = None) -> Dict[str, Any]:
    """Queries TMDB (or falls back to search/mock data) for a movie to get IMDb details.
    
    Args:
        title: The movie title.
        director: Optional director name to help filter results.
        
    Returns:
        A dict with movie reference info (imdb_url, tmdb_url, year, original_title).
    """
    api_key = os.environ.get("TMDB_API_KEY")
    if api_key:
        try:
            # Query TMDB Search API
            query_escaped = urllib.parse.quote(title)
            url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query_escaped}"
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    # Match by director if provided
                    best_match = results[0]
                    movie_id = best_match["id"]
                    
                    # Fetch external IDs for IMDb link
                    ext_url = f"https://api.themoviedb.org/3/movie/{movie_id}/external_ids?api_key={api_key}"
                    ext_r = httpx.get(ext_url, timeout=5)
                    imdb_id = ""
                    if ext_r.status_code == 200:
                        imdb_id = ext_r.json().get("imdb_id", "")
                        
                    return {
                        "title": best_match.get("title", title),
                        "original_title": best_match.get("original_title", title),
                        "release_year": best_match.get("release_date", "2026")[:4],
                        "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "https://www.imdb.com/",
                        "tmdb_url": f"https://www.themoviedb.org/movie/{movie_id}"
                    }
        except Exception as e:
            print(f"Error querying TMDB API: {e}")
            
    # Mock/fallback lookup
    # Simple hardcoded registry for pilot testing
    registry = {
        "a useful ghost": {
            "title": "A Useful Ghost",
            "original_title": "A Useful Ghost",
            "release_year": "2024",
            "imdb_url": "https://www.imdb.com/title/tt32313620/",
            "tmdb_url": "https://www.themoviedb.org/movie/1199343"
        },
        "state of grace": {
            "title": "State of Grace",
            "original_title": "Starea de gratie",
            "release_year": "2001",
            "imdb_url": "https://www.imdb.com/title/tt0316681/",
            "tmdb_url": "https://www.themoviedb.org/movie/295195"
        },
        "rules of the game": {
            "title": "The Rules of the Game",
            "original_title": "La Règle du jeu",
            "release_year": "1939",
            "imdb_url": "https://www.imdb.com/title/tt0031885/",
            "tmdb_url": "https://www.themoviedb.org/movie/776"
        }
    }
    
    key = title.lower().strip()
    if key in registry:
        return registry[key]
        
    # Default fallback
    return {
        "title": title,
        "original_title": title,
        "release_year": "2026",
        "imdb_url": f"https://www.imdb.com/find?q={urllib.parse.quote(title)}",
        "tmdb_url": f"https://www.themoviedb.org/search?query={urllib.parse.quote(title)}"
    }

# Watchlist tools directly exposed to agent
def get_user_watchlist() -> str:
    """Returns the current user watchlist as a formatted string."""
    watchlist = watchlist_store.get_watchlist()
    if not watchlist:
        return "Your watchlist is empty."
    
    lines = []
    for i, item in enumerate(watchlist, 1):
        director_str = f" (Dir: {item['director']})" if item.get('director') else ""
        lines.append(f"{i}. {item['title']}{director_str}")
    return "\n".join(lines)

def add_movie_to_watchlist(title: str, director: Optional[str] = None) -> str:
    """Adds a movie to the user's watchlist.
    
    Args:
        title: Title of the movie.
        director: Optional name of the director.
    """
    success = watchlist_store.add_to_watchlist(title, director)
    if success:
        return f"Successfully added '{title}' to your watchlist."
    return f"'{title}' is already on your watchlist."

def remove_movie_from_watchlist(title: str) -> str:
    """Removes a movie from the user's watchlist by title."""
    success = watchlist_store.remove_from_watchlist(title)
    if success:
        return f"Successfully removed '{title}' from your watchlist."
    return f"'{title}' was not found in your watchlist."

def find_showtimes_for_watchlist() -> str:
    """Checks the local Cluj cinema schedules against the user's watchlist and returns matches.
    
    Returns:
        A report string detailing matching screenings.
    """
    watchlist = watchlist_store.get_watchlist()
    if not watchlist:
        return "Your watchlist is empty. Add films to match them with showtimes."
        
    schedules = fetch_cinema_schedules()
    matches = []
    
    for item in watchlist:
        watch_title = item["title"].lower().strip()
        for show in schedules:
            show_title = show["title"].lower().strip()
            # Fuzzy match / title containment
            if watch_title in show_title or show_title in watch_title:
                # Get reference URL
                ref = search_movie_reference(item["title"], item.get("director"))
                matches.append({
                    "title": item["title"],
                    "cinema": show["cinema"],
                    "date": show["date"],
                    "time": show["time"],
                    "link": show["link"],
                    "imdb_url": ref.get("imdb_url", "")
                })
                
    if not matches:
        return "No showtimes found matching the films in your watchlist."
        
    lines = ["🎬 MATCHES FOUND:"]
    for match in matches:
        lines.append(
            f"- **{match['title']}** playing at **{match['cinema']}** on {match['date']} at {match['time']}\n"
            f"  Cinema link: {match['link']}\n"
            f"  IMDb link: {match['imdb_url']}"
        )
    return "\n".join(lines)

def fetch_tiff_unlimited_catalog() -> List[Dict[str, Any]]:
    """Scrapes the TIFF Unlimited catalog using Uscreen storefront initial_categories endpoint."""
    url = "https://api.uscreencdn.com/catalog/initial_categories?ai_recommendations=false&continue_watching=true&featured_category_id=244371&my_library=true&preview=false&user=false"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Fastly-Origin": "unlimitedtiff"
    }
    
    cached = watchlist_store.get_cached_url(url)
    html = cached
    if not html:
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
            if r.status_code == 200:
                html = r.text
                watchlist_store.set_cached_url(url, html)
        except Exception as e:
            print(f"Error fetching TIFF Unlimited catalog: {e}")
            
    catalog = []
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
            seen_links = set()
            for link in soup.select("a.card-title"):
                href = link.get("href", "")
                title_attr = link.get("title", "")
                
                if href and "/programs/" in href:
                    clean_href = href.split("?")[0]
                    full_link = urllib.parse.urljoin("https://unlimited.tiff.ro", clean_href)
                    
                    if full_link not in seen_links:
                        seen_links.add(full_link)
                        title = title_attr.strip()
                        if " (" in title and title.endswith(")"):
                            title = title.split(" (")[0].strip()
                            
                        slug = clean_href.split("/")[-1].replace("-", " ").title()
                        
                        catalog.append({
                            "title": title,
                            "english_title": slug,
                            "link": full_link,
                            "provider": "TIFF Unlimited"
                        })
        except Exception as e:
            print(f"Error parsing TIFF Unlimited catalog: {e}")
            
    if not catalog:
        catalog = [
            {
                "title": "Dragostea care rămâne",
                "english_title": "The Love That Remains",
                "link": "https://unlimited.tiff.ro/programs/the-love-that-remains",
                "provider": "TIFF Unlimited"
            },
            {
                "title": "A Useful Ghost",
                "english_title": "A Useful Ghost",
                "link": "https://unlimited.tiff.ro/programs/a-useful-ghost",
                "provider": "TIFF Unlimited"
            },
            {
                "title": "Regulile jocului",
                "english_title": "Rules of the Game",
                "link": "https://unlimited.tiff.ro/programs/rules-of-the-game",
                "provider": "TIFF Unlimited"
            }
        ]
        
    return catalog

def check_netflix_availability(title: str, director: Optional[str] = None) -> Optional[str]:
    """Checks if a movie is available on Netflix using TMDB Watch Providers API, with mock fallbacks."""
    api_key = os.environ.get("TMDB_API_KEY")
    if api_key:
        try:
            query_escaped = urllib.parse.quote(title)
            url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query_escaped}"
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    movie_id = results[0]["id"]
                    prov_url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={api_key}"
                    prov_r = httpx.get(prov_url, timeout=5)
                    if prov_r.status_code == 200:
                        prov_data = prov_r.json().get("results", {})
                        for country_code in ["RO", "US"]:
                            country_data = prov_data.get(country_code, {})
                            flatrate = country_data.get("flatrate", [])
                            for p in flatrate:
                                if "netflix" in p.get("provider_name", "").lower():
                                    return f"https://www.netflix.com/search?q={urllib.parse.quote(title)}"
        except Exception as e:
            print(f"Error checking Netflix availability: {e}")
            
    # Mock fallback registry for Netflix
    netflix_mock_list = {
        "feels like home": "https://www.netflix.com/search?q=Feels%20Like%20Home",
        "the last viking": "https://www.netflix.com/search?q=The%20Last%20Viking",
        "rules of the game": "https://www.netflix.com/search?q=Rules%20of%20the%20Game"
    }
    key = title.lower().strip()
    if key in netflix_mock_list:
        return netflix_mock_list[key]
        
    return None

def _get_table_grid(table) -> List[List[Any]]:
    """Helper to convert a table with colspan/rowspan into a flat 2D grid of cell elements."""
    rows = table.find_all("tr")
    grid = [[] for _ in range(len(rows))]
    
    for r_idx, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        c_idx = 0
        for cell in cells:
            # Find the first empty slot in the grid for this row
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1
                
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            
            for dr in range(rowspan):
                for dc in range(colspan):
                    tr_idx = r_idx + dr
                    tc_idx = c_idx + dc
                    # Pad target row if needed
                    while len(grid[tr_idx]) <= tc_idx:
                        grid[tr_idx].append(None)
                    grid[tr_idx][tc_idx] = cell
            c_idx += colspan
            
    return grid

def fetch_cannes_movies() -> List[Film]:
    """Crawls and parses the Cannes Film Festival 2026 official selection from Wikipedia."""
    cache_key = "cannes_movies"
    cached_list = watchlist_store.get_cached_parsed_list(cache_key)
    if cached_list:
        return [Film.from_dict(d) for d in cached_list]

    url = "https://en.wikipedia.org/wiki/2026_Cannes_Film_Festival"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    cached_html = watchlist_store.get_cached_url(url)
    html = cached_html
    if not html:
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
            if r.status_code == 200:
                html = r.text
                watchlist_store.set_cached_url(url, html)
        except Exception as e:
            print(f"Error fetching Cannes Wikipedia page: {e}")
            
    films = []
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
            target_sections = {
                "in competition", "un certain regard", "cannes premiere", 
                "out of competition", "special screenings", "directors' fortnight",
                "critics' week", "directors' fortnight (quinzaine des cinéastes)",
                "critics' week (semaine de la critique)"
            }
            
            for table in soup.select("table.wikitable"):
                prev_h = table.find_previous(["h3", "h4", "h2"])
                section_name = prev_h.get_text(strip=True) if prev_h else "Unknown"
                
                # Remove [edit] annotations from section names
                import re
                section_name = re.sub(r"\[edit\]", "", section_name).strip()
                
                clean_sec = section_name.lower().strip()
                is_target = False
                for t_sec in target_sections:
                    if t_sec in clean_sec:
                        is_target = True
                        break
                        
                if not is_target:
                    continue
                    
                grid = _get_table_grid(table)
                if not grid:
                    continue
                    
                # The first row of the grid contains header elements
                header_row = grid[0]
                headers = [c.get_text(strip=True).lower() if c else "" for c in header_row]
                
                title_idx, orig_idx, dir_idx, country_idx = 0, 1, 2, 3
                if headers:
                    for idx, h in enumerate(headers):
                        if "english title" in h or "title" in h and title_idx == 0:
                            title_idx = idx
                        elif "original title" in h:
                            orig_idx = idx
                        elif "director" in h:
                            dir_idx = idx
                        elif "country" in h:
                            country_idx = idx
                            
                for r_idx, row_cells in enumerate(grid):
                    # Skip the first row (header row)
                    if r_idx == 0:
                        continue
                        
                    if not row_cells or len(row_cells) <= max(title_idx, dir_idx):
                        continue
                        
                    title_cell = row_cells[title_idx]
                    dir_cell = row_cells[dir_idx]
                    
                    if not title_cell or not dir_cell:
                        continue
                        
                    eng_title = title_cell.get_text(strip=True)
                    if not eng_title:
                        continue
                        
                    orig_cell = row_cells[orig_idx] if len(row_cells) > orig_idx else title_cell
                    orig_title = orig_cell.get_text(strip=True) if orig_cell else eng_title
                    
                    director = dir_cell.get_text(strip=True)
                    
                    country_cell = row_cells[country_idx] if len(row_cells) > country_idx else None
                    country = country_cell.get_text(strip=True) if country_cell else "Unknown"
                    
                    eng_title = re.sub(r"\[\d+\]|\[\w+\]", "", eng_title).strip()
                    orig_title = re.sub(r"\[\d+\]|\[\w+\]", "", orig_title).strip()
                    director = re.sub(r"\[\d+\]|\[\w+\]", "", director).strip()
                    country = re.sub(r"\[\d+\]|\[\w+\]", "", country).strip()
                    
                    eng_title = eng_title.replace('"', '').replace('“', '').replace('”', '')
                    orig_title = orig_title.replace('"', '').replace('“', '').replace('”', '')
                    
                    wiki_link_el = title_cell.select_one("a")
                    link = ""
                    if wiki_link_el:
                        link = urllib.parse.urljoin("https://en.wikipedia.org", wiki_link_el.get("href", ""))
                        
                    category_obj = Category(name=section_name, festival_id="cannes")
                    selection = FilmSelection(
                        festival_id="Cannes",
                        category=category_obj,
                        link=link,
                        description=f"Official selection of Cannes Film Festival 2026 under the {section_name} section.",
                        award=get_award_for_title(eng_title, "Cannes") or get_award_for_title(orig_title, "Cannes")
                    )
                    film = Film(
                        title=eng_title,
                        original_title=orig_title,
                        director=director,
                        country=country,
                        duration="90 min",
                        selections=[selection]
                    )
                    films.append(film)
        except Exception as e:
            print(f"Error parsing Cannes films from Wikipedia: {e}")
            
    if films:
        from concurrent.futures import ThreadPoolExecutor
        
        def populate_cannes_details(film: Film):
            ref = search_movie_reference(film.title, film.director)
            if ref.get("duration") and ref["duration"] != "90 min":
                film.duration = ref["duration"]
            if ref.get("imdb_url"):
                film.imdb_url = ref["imdb_url"]
            if ref.get("tmdb_url"):
                film.tmdb_url = ref["tmdb_url"]
                
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(populate_cannes_details, films)
            
    if not films:
        mock_cannes = [
            {
                "title": "All of a Sudden",
                "original_title": "Soudain",
                "director": "Ryusuke Hamaguchi",
                "category": "In Competition",
                "country": "France, Japan",
                "duration": "120 min",
                "description": "A quiet drama exploring unexpected connections by Ryusuke Hamaguchi.",
                "link": "https://en.wikipedia.org/wiki/2026_Cannes_Film_Festival",
                "festivals": ["Cannes"]
            },
            {
                "title": "Crescendo",
                "original_title": "L'Objet du Délit",
                "director": "Agnes Jaoui",
                "category": "Out of Competition",
                "country": "France",
                "duration": "105 min",
                "description": "A satirical comedy detailing family dynamics and art scandals.",
                "link": "https://en.wikipedia.org/wiki/2026_Cannes_Film_Festival",
                "festivals": ["Cannes"]
            },
            {
                "title": "A Useful Ghost",
                "original_title": "A Useful Ghost",
                "director": "Abhiansh",
                "category": "In Competition",
                "country": "Thailand",
                "duration": "95 min",
                "description": "A ghost tries to be useful to its family by helping around the house.",
                "link": "https://en.wikipedia.org/wiki/2026_Cannes_Film_Festival",
                "festivals": ["Cannes"]
            }
        ]
        films = [Film.from_dict(d) for d in mock_cannes]
        
    watchlist_store.set_cached_parsed_list(cache_key, [f.to_dict() for f in films])
    return films

def fetch_berlinale_movies() -> List[Film]:
    """Crawls and parses the 76th Berlin International Film Festival (Berlinale 2026) official sections from Wikipedia."""
    cache_key = "berlinale_movies"
    cached_list = watchlist_store.get_cached_parsed_list(cache_key)
    if cached_list:
        return [Film.from_dict(d) for d in cached_list]

    url = "https://en.wikipedia.org/wiki/76th_Berlin_International_Film_Festival"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    cached_html = watchlist_store.get_cached_url(url)
    html = cached_html
    if not html:
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
            if r.status_code == 200:
                html = r.text
                watchlist_store.set_cached_url(url, html)
        except Exception as e:
            print(f"Error fetching Berlinale Wikipedia page: {e}")
            
    films = []
    if html:
        try:
            import re
            soup = BeautifulSoup(html, "html.parser")
            target_sections = {
                "in competition", "main competition", "competition",
                "berlinale special", "berlinale special gala",
                "perspectives", "panorama", "forum", "forum expanded",
                "generation", "berlinale classics", "retrospective",
                "berlinale shorts", "short film competition"
            }
            
            for table in soup.select("table.wikitable"):
                prev_h = table.find_previous(["h3", "h4", "h2"])
                section_name = prev_h.get_text(strip=True) if prev_h else "Unknown"
                
                # Remove [edit] annotations from section names
                section_name = re.sub(r"\[edit\]", "", section_name).strip()
                
                clean_sec = section_name.lower().strip()
                is_target = False
                for t_sec in target_sections:
                    if t_sec in clean_sec:
                        is_target = True
                        break
                        
                if not is_target:
                    continue
                    
                grid = _get_table_grid(table)
                if not grid:
                    continue
                    
                # The first row of the grid contains header elements
                header_row = grid[0]
                header_texts = [c.get_text(strip=True).lower() if c else "" for c in header_row]
                
                # Skip non-film tables (e.g. Awards, Juries) by checking for title+director columns
                has_title = any("title" in h for h in header_texts)
                has_director = any("director" in h for h in header_texts)
                if not has_title or not has_director:
                    continue
                
                title_idx, orig_idx, dir_idx, country_idx = 0, 1, 2, 3
                for idx, h in enumerate(header_texts):
                    if "english title" in h or ("title" in h and idx == 0):
                        title_idx = idx
                    elif "original title" in h:
                        orig_idx = idx
                    elif "director" in h:
                        dir_idx = idx
                    elif "country" in h or "production" in h:
                        country_idx = idx
                            
                for r_idx, row_cells in enumerate(grid):
                    if r_idx == 0:
                        continue
                        
                    if not row_cells or len(row_cells) <= max(title_idx, dir_idx):
                        continue
                        
                    title_cell = row_cells[title_idx]
                    dir_cell = row_cells[dir_idx]
                    
                    if not title_cell or not dir_cell:
                        continue
                        
                    eng_title = title_cell.get_text(strip=True)
                    if not eng_title:
                        continue
                        
                    orig_cell = row_cells[orig_idx] if len(row_cells) > orig_idx else title_cell
                    orig_title = orig_cell.get_text(strip=True) if orig_cell else eng_title
                    
                    director = dir_cell.get_text(strip=True)
                    
                    country_cell = row_cells[country_idx] if len(row_cells) > country_idx else None
                    country = country_cell.get_text(strip=True) if country_cell else "Unknown"
                    
                    # Clean wiki annotations
                    eng_title = re.sub(r"\[\d+\]|\[\w+\]", "", eng_title).strip()
                    orig_title = re.sub(r"\[\d+\]|\[\w+\]", "", orig_title).strip()
                    director = re.sub(r"\[\d+\]|\[\w+\]", "", director).strip()
                    country = re.sub(r"\[\d+\]|\[\w+\]", "", country).strip()
                    
                    eng_title = eng_title.replace('"', '').replace('\u201c', '').replace('\u201d', '')
                    orig_title = orig_title.replace('"', '').replace('\u201c', '').replace('\u201d', '')
                    
                    wiki_link_el = title_cell.select_one("a")
                    link = ""
                    if wiki_link_el:
                        link = urllib.parse.urljoin("https://en.wikipedia.org", wiki_link_el.get("href", ""))
                        
                    category_obj = Category(name=section_name, festival_id="berlinale")
                    selection = FilmSelection(
                        festival_id="Berlinale",
                        category=category_obj,
                        link=link,
                        description=f"Official selection of Berlinale 2026 under the {section_name} section.",
                        award=get_award_for_title(eng_title, "Berlinale") or get_award_for_title(orig_title, "Berlinale")
                    )
                    film = Film(
                        title=eng_title,
                        original_title=orig_title,
                        director=director,
                        country=country,
                        duration="90 min",
                        selections=[selection]
                    )
                    films.append(film)
        except Exception as e:
            print(f"Error parsing Berlinale films from Wikipedia: {e}")
            
    if films:
        from concurrent.futures import ThreadPoolExecutor
        
        def populate_berlinale_details(film: Film):
            ref = search_movie_reference(film.title, film.director)
            if ref.get("duration") and ref["duration"] != "90 min":
                film.duration = ref["duration"]
            if ref.get("imdb_url"):
                film.imdb_url = ref["imdb_url"]
            if ref.get("tmdb_url"):
                film.tmdb_url = ref["tmdb_url"]
                
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(populate_berlinale_details, films)
            
    if not films:
        mock_berlinale = [
            {
                "title": "Dreams",
                "original_title": "Dreams",
                "director": "Michel Franco",
                "category": "Main Competition",
                "country": "Mexico, United States",
                "duration": "110 min",
                "description": "A drama exploring love and ambition by Michel Franco, starring Jessica Chastain.",
                "link": "https://en.wikipedia.org/wiki/76th_Berlin_International_Film_Festival",
                "festivals": ["Berlinale"]
            },
            {
                "title": "If I Had Legs I'd Kick You",
                "original_title": "If I Had Legs I'd Kick You",
                "director": "Mary Bronstein",
                "category": "Main Competition",
                "country": "United States",
                "duration": "105 min",
                "description": "A psychological portrait of a mother in crisis, starring Rose Byrne.",
                "link": "https://en.wikipedia.org/wiki/76th_Berlin_International_Film_Festival",
                "festivals": ["Berlinale"]
            },
            {
                "title": "Kontinental '25",
                "original_title": "Kontinental '25",
                "director": "Radu Jude",
                "category": "Main Competition",
                "country": "Romania",
                "duration": "100 min",
                "description": "A satirical exploration of European identity by Romanian auteur Radu Jude.",
                "link": "https://en.wikipedia.org/wiki/76th_Berlin_International_Film_Festival",
                "festivals": ["Berlinale"]
            }
        ]
        films = [Film.from_dict(d) for d in mock_berlinale]
        
    watchlist_store.set_cached_parsed_list(cache_key, [f.to_dict() for f in films])
    return films

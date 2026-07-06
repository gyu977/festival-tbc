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
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re
import difflib

def normalize_str(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())

AWARD_WINNERS = {
    "TIFF": {
        "lionel": "Transilvania Trophy (TIFF)",
        "titanic ocean": "Best Director Award (TIFF)",
        "the father": "Special Jury Award (TIFF)",
        "truly naked": "Best Performance Award (TIFF)",
        "feels like home": "Audience Award (TIFF)",
    },
    "Cannes": {
        "fjord": "Palme d'Or (Cannes)",
        "minotaur": "Grand Prix (Cannes)",
        "the dreamed adventure": "Jury Prize (Cannes)",
        "the black ball": "Best Director (Cannes)",
        "fatherland": "Best Director (Cannes)",
        "everytime": "Un Certain Regard Prize (Cannes)",
        "elephants in the fog": "Un Certain Regard Jury Prize (Cannes)",
        "iron boy": "Un Certain Regard Special Jury Prize (Cannes)",
    },
    "Berlinale": {
        "gelbe briefe": "Golden Bear for Best Film (Berlinale)",
        "yellow letters": "Golden Bear for Best Film (Berlinale)",
        "kurtulus": "Silver Bear Grand Jury Prize (Berlinale)",
        "salvation": "Silver Bear Grand Jury Prize (Berlinale)",
        "queen at sea": "Silver Bear Jury Prize (Berlinale)",
        "everybody digs bill evans": "Silver Bear for Best Director (Berlinale)",
        "rose": "Silver Bear for Best Leading Performance (Berlinale)",
        "nina roza": "Silver Bear for Best Screenplay (Berlinale)",
        "yo": "Silver Bear for Outstanding Artistic Contribution (Berlinale)",
        "love is a rebellious bird": "Silver Bear for Outstanding Artistic Contribution (Berlinale)",
        "if pigeons turned to gold": "Berlinale Documentary Award (Berlinale)"
    }
}

def get_award_for_title(title: str, festival_id: Optional[str] = None) -> Optional[str]:
    title_key = normalize_str(title)
    if festival_id:
        fest_key = festival_id
        if fest_key.lower() == "tiff":
            fest_key = "TIFF"
        elif fest_key.lower() == "cannes":
            fest_key = "Cannes"
        elif fest_key.lower() == "berlinale":
            fest_key = "Berlinale"
        fest_winners = AWARD_WINNERS.get(fest_key, {})
        for k, v in fest_winners.items():
            if normalize_str(k) == title_key:
                return v
        return None
    
    for fest_key, fest_winners in AWARD_WINNERS.items():
        for k, v in fest_winners.items():
            if normalize_str(k) == title_key:
                return v
    return None

@dataclass(frozen=True)
class Category:
    name: str
    festival_id: str

@dataclass(frozen=True)
class FilmSelection:
    festival_id: str
    category: Category
    link: str
    description: str
    award: Optional[str] = None

@dataclass
class Film:
    title: str
    director: str
    original_title: str
    country: str
    duration: str
    selections: List[FilmSelection] = field(default_factory=list)
    imdb_url: Optional[str] = None
    tmdb_url: Optional[str] = None

    @property
    def identity(self) -> str:
        """Determines the domain identity string based on title and director."""
        title_norm = normalize_str(self.title)
        dir_norm = normalize_str(self.director) if self.director else "unknown"
        return f"{title_norm}::{dir_norm}"

    @property
    def festivals(self) -> List[str]:
        return [sel.festival_id for sel in self.selections]

    def is_same_as(self, other: "Film") -> bool:
        """Domain logic to evaluate film equivalence (fuzzy & ID checks)."""
        # 1. Match by exact normalized title
        t1_norm = normalize_str(self.title)
        t2_norm = normalize_str(other.title)
        if t1_norm and t1_norm == t2_norm:
            return True
            
        # 2. Match by original title
        ot1_norm = normalize_str(self.original_title)
        ot2_norm = normalize_str(other.original_title)
        if (ot1_norm and ot1_norm == t2_norm) or (t1_norm and t1_norm == ot2_norm) or (ot1_norm and ot1_norm == ot2_norm):
            return True
            
        # 3. Match by director and fuzzy title similarity
        d1_norm = normalize_str(self.director)
        d2_norm = normalize_str(other.director)
        if d1_norm and d2_norm and d1_norm == d2_norm:
            title_ratio = difflib.SequenceMatcher(None, self.title.lower(), other.title.lower()).ratio()
            if title_ratio >= 0.8:
                return True
                
        # 4. Match by TMDB/IMDb URL
        if self.imdb_url and other.imdb_url and self.imdb_url != "https://www.imdb.com/" and self.imdb_url == other.imdb_url:
            return True
        if self.tmdb_url and other.tmdb_url and self.tmdb_url == other.tmdb_url:
            return True
            
        return False

    def add_selection(self, new_selection: FilmSelection):
        if new_selection.festival_id not in self.festivals:
            self.selections.append(new_selection)
        else:
            # If selection already exists for this festival, update award/metadata if richer
            for idx, sel in enumerate(self.selections):
                if sel.festival_id == new_selection.festival_id:
                    if new_selection.award and not sel.award:
                        self.selections[idx] = FilmSelection(
                            festival_id=sel.festival_id,
                            category=sel.category,
                            link=sel.link or new_selection.link,
                            description=sel.description or new_selection.description,
                            award=new_selection.award
                        )
                        break

    def to_dict(self) -> Dict[str, Any]:
        """Converts the Film entity to a backwards-compatible dictionary format for the frontend."""
        desc = ""
        link = ""
        categories = []
        awards = []
        for sel in self.selections:
            if not desc and sel.description:
                desc = sel.description
            if not link and sel.link:
                link = sel.link
            if sel.category.name:
                categories.append(sel.category.name)
            if sel.award:
                awards.append(sel.award)
        
        # Serialize selections for cached restoration
        serialized_selections = []
        for sel in self.selections:
            serialized_selections.append({
                "festival_id": sel.festival_id,
                "category": {
                    "name": sel.category.name,
                    "festival_id": sel.category.festival_id
                },
                "link": sel.link,
                "description": sel.description,
                "award": sel.award
            })
        
        # Deduplicate
        unique_categories = list(dict.fromkeys(categories))
        unique_awards = list(dict.fromkeys(awards))
        
        return {
            "title": self.title,
            "original_title": self.original_title,
            "director": self.director,
            "category": " / ".join(unique_categories) if unique_categories else "General",
            "duration": self.duration,
            "description": desc or f"Official selection of {', '.join(self.festivals)}.",
            "link": link,
            "country": self.country,
            "festivals": self.festivals,
            "imdb_url": self.imdb_url or f"https://www.imdb.com/find?q={self.title}",
            "tmdb_url": self.tmdb_url or "",
            "selections": serialized_selections,
            "awards": unique_awards
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Film":
        """Deserializes a dictionary back into a Film entity."""
        selections = []
        raw_selections = data.get("selections", [])
        title = data.get("title", "")
        fallback_award = get_award_for_title(title)
        
        if raw_selections:
            for s in raw_selections:
                cat_data = s.get("category", {})
                category = Category(name=cat_data.get("name", ""), festival_id=cat_data.get("festival_id", ""))
                festival_id = s.get("festival_id", "")
                selections.append(FilmSelection(
                    festival_id=festival_id,
                    category=category,
                    link=s.get("link", ""),
                    description=s.get("description", ""),
                    award=s.get("award") or get_award_for_title(title, festival_id)
                ))
        else:
            # Fallback for old cache format
            festivals = data.get("festivals", [])
            for f in festivals:
                category = Category(name=data.get("category", ""), festival_id=f.lower())
                selections.append(FilmSelection(
                    festival_id=f,
                    category=category,
                    link=data.get("link", ""),
                    description=data.get("description", ""),
                    award=fallback_award
                ))
                
        return cls(
            title=data.get("title", ""),
            director=data.get("director", ""),
            original_title=data.get("original_title", ""),
            country=data.get("country", ""),
            duration=data.get("duration", "90 min"),
            selections=selections,
            imdb_url=data.get("imdb_url"),
            tmdb_url=data.get("tmdb_url")
        )

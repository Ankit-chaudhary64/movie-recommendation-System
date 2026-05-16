from __future__ import annotations

import argparse
import difflib
import html
import json
import mimetypes
import pickle
import re
import threading
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MOVIE_PATH = BASE_DIR / "movie_list.pkl"
SIMILARITY_PATH = BASE_DIR / "similarity.pkl"
TMDB_PAGE_URL = "https://www.themoviedb.org/movie/{movie_id}?language=en-US"

FEATURED_TITLES = [
    "Avatar",
    "The Dark Knight",
    "Inception",
    "Interstellar",
    "The Avengers",
    "The Matrix",
    "Titanic",
    "Jurassic Park",
    "Iron Man",
    "Spectre",
]

POSTER_PATTERNS = (
    re.compile(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(r"https://media\.themoviedb\.org/t/p/[^\"'<> ]+", re.IGNORECASE),
    re.compile(r"https://image\.tmdb\.org/t/p/[^\"'<> ]+", re.IGNORECASE),
)


def shorten_text(text: str, word_limit: int = 28) -> str:
    words = text.split()
    if len(words) <= word_limit:
        return " ".join(words)
    return " ".join(words[:word_limit]).rstrip(",.;:") + "..."


def humanize_token(token: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", token.strip())
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    if cleaned.islower():
        return cleaned.title()
    return cleaned


def split_story_and_keywords(tags: str) -> tuple[str, list[str]]:
    text = " ".join(tags.split())
    if not text:
        return "No summary available for this movie yet.", []

    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    summary = parts[0].strip() if parts else text
    if not re.search(r"[.!?]$", summary):
        summary = shorten_text(summary, word_limit=24)

    keyword_source = parts[1] if len(parts) > 1 else text
    keywords: list[str] = []
    seen: set[str] = set()

    for raw_token in keyword_source.split():
        token = humanize_token(raw_token)
        normalized = token.casefold()
        if len(token) < 4 or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(token)
        if len(keywords) == 4:
            break

    return summary, keywords


class MovieRecommender:
    def __init__(self, movie_path: Path, similarity_path: Path) -> None:
        self.movies = pd.read_pickle(movie_path).copy()
        with similarity_path.open("rb") as file:
            self.similarity = np.asarray(pickle.load(file), dtype=np.float32)
        self._validate()

        self.movies = self.movies.reset_index(drop=True)
        self.movies["movie_id"] = self.movies["movie_id"].astype(int)
        self.movies["title"] = self.movies["title"].fillna("").astype(str)
        self.movies["tags"] = self.movies["tags"].fillna("").astype(str)

        self.titles = self.movies["title"].tolist()
        self.title_lookup: dict[str, int] = {}
        for index, title in enumerate(self.titles):
            self.title_lookup.setdefault(title.casefold(), index)

        self.unique_title_keys = list(self.title_lookup.keys())
        self.poster_cache: dict[int, str] = {}
        self.poster_lock = threading.Lock()
        self.featured = self._build_featured()

    def _validate(self) -> None:
        required_columns = {"movie_id", "title", "tags"}
        if not isinstance(self.movies, pd.DataFrame):
            raise TypeError("movie_list.pkl must contain a pandas DataFrame.")
        if not required_columns.issubset(self.movies.columns):
            missing = ", ".join(sorted(required_columns - set(self.movies.columns)))
            raise ValueError(f"movie_list.pkl is missing columns: {missing}")
        if self.similarity.ndim != 2:
            raise ValueError("similarity.pkl must contain a 2D similarity matrix.")
        movie_count = len(self.movies)
        if self.similarity.shape != (movie_count, movie_count):
            raise ValueError(
                "similarity.pkl shape does not match the number of movies in movie_list.pkl."
            )

    def _build_featured(self) -> list[dict[str, Any]]:
        picks: list[dict[str, Any]] = []
        seen: set[str] = set()

        for title in FEATURED_TITLES:
            index = self.title_lookup.get(title.casefold())
            if index is None:
                continue
            seen.add(self.titles[index].casefold())
            picks.append(self.movie_payload(index))

        for index in range(min(14, len(self.movies))):
            title_key = self.titles[index].casefold()
            if title_key in seen:
                continue
            seen.add(title_key)
            picks.append(self.movie_payload(index))
            if len(picks) == 10:
                break

        return picks[:10]

    def movie_payload(
        self,
        index: int,
        *,
        score: float | None = None,
        rank: int | None = None,
    ) -> dict[str, Any]:
        row = self.movies.iloc[index]
        summary, keywords = split_story_and_keywords(row["tags"])
        movie_id = int(row["movie_id"])
        payload: dict[str, Any] = {
            "movie_id": movie_id,
            "title": row["title"],
            "summary": summary,
            "highlights": keywords,
            "poster": f"/api/poster/{movie_id}",
        }
        if score is not None:
            payload["score"] = round(float(score) * 100, 1)
        if rank is not None:
            payload["rank"] = rank
        return payload

    def poster_url(self, movie_id: int) -> str | None:
        with self.poster_lock:
            cached = self.poster_cache.get(movie_id)
        if cached:
            return cached

        poster_url = self._fetch_poster_url(movie_id)
        if poster_url:
            with self.poster_lock:
                self.poster_cache[movie_id] = poster_url
        return poster_url

    def _fetch_poster_url(self, movie_id: int) -> str | None:
        request = urllib.request.Request(
            TMDB_PAGE_URL.format(movie_id=movie_id),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                html_text = response.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

        for pattern in POSTER_PATTERNS:
            match = pattern.search(html_text)
            if not match:
                continue
            raw_url = match.group(1) if match.groups() else match.group(0)
            cleaned_url = html.unescape(raw_url).replace("&amp;", "&")
            if cleaned_url.startswith("//"):
                cleaned_url = f"https:{cleaned_url}"
            return cleaned_url

        return None

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        normalized = query.strip().casefold()
        if not normalized:
            return self.featured[:limit]

        candidates: list[tuple[int, int, str, int]] = []
        for index, title in enumerate(self.titles):
            folded = title.casefold()
            if folded == normalized:
                rank = 0
            elif folded.startswith(normalized):
                rank = 1
            elif normalized in folded:
                rank = 2
            else:
                continue
            candidates.append((rank, len(title), title, index))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for _, _, _, index in candidates:
            title_key = self.titles[index].casefold()
            if title_key in seen:
                continue
            seen.add(title_key)
            results.append(self.movie_payload(index))
            if len(results) == limit:
                return results

        if len(results) < limit:
            close_matches = difflib.get_close_matches(
                normalized,
                self.unique_title_keys,
                n=limit - len(results),
                cutoff=0.62,
            )
            for match_key in close_matches:
                if match_key in seen:
                    continue
                seen.add(match_key)
                results.append(self.movie_payload(self.title_lookup[match_key]))
                if len(results) == limit:
                    break

        return results

    def random_pick(self) -> dict[str, Any]:
        index = int(np.random.randint(0, len(self.movies)))
        return self.movie_payload(index)

    def resolve_title(self, query: str) -> tuple[int, bool]:
        normalized = query.strip().casefold()
        if not normalized:
            raise ValueError("Enter a movie title to get recommendations.")

        exact_index = self.title_lookup.get(normalized)
        if exact_index is not None:
            return exact_index, True

        close_matches = difflib.get_close_matches(normalized, self.unique_title_keys, n=1, cutoff=0.6)
        if close_matches:
            return self.title_lookup[close_matches[0]], False

        raise LookupError(f'No movie found for "{query.strip()}".')

    def recommend(self, query: str, limit: int = 8) -> dict[str, Any]:
        index, exact_match = self.resolve_title(query)
        scores = self.similarity[index]
        sorted_indexes = np.argsort(scores)[::-1]

        recommendations: list[dict[str, Any]] = []
        for candidate_index in sorted_indexes:
            if candidate_index == index:
                continue
            recommendations.append(
                self.movie_payload(
                    int(candidate_index),
                    score=float(scores[candidate_index]),
                    rank=len(recommendations) + 1,
                )
            )
            if len(recommendations) == limit:
                break

        movie = self.movie_payload(index)
        return {
            "requested_title": query,
            "matched_title": movie["title"],
            "exact_match": exact_match,
            "movie": movie,
            "recommendations": recommendations,
        }


class RecommendationHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        recommender: MovieRecommender,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.recommender = recommender


class MovieRequestHandler(BaseHTTPRequestHandler):
    server: RecommendationHTTPServer

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", content_type="text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            self.serve_static(path)
            return
        if path.startswith("/api/poster/"):
            movie_id = path.removeprefix("/api/poster/").strip("/")
            self.serve_poster(movie_id)
            return
        if path == "/api/health":
            self.send_json(
                {
                    "status": "ok",
                    "movie_count": len(self.server.recommender.movies),
                    "featured_count": len(self.server.recommender.featured),
                }
            )
            return
        if path == "/api/featured":
            self.send_json({"featured": self.server.recommender.featured})
            return
        if path == "/api/random":
            self.send_json({"movie": self.server.recommender.random_pick()})
            return
        if path == "/api/suggestions":
            query = params.get("q", [""])[0]
            self.send_json({"results": self.server.recommender.suggestions(query)})
            return
        if path == "/api/recommend":
            query = params.get("movie", [""])[0]
            try:
                payload = self.server.recommender.recommend(query)
            except ValueError as error:
                self.send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except LookupError as error:
                self.send_json(
                    {
                        "error": str(error),
                        "suggestions": self.server.recommender.suggestions(query, limit=6),
                    },
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self.send_json(payload)
            return

        self.send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def serve_poster(self, movie_id_text: str) -> None:
        if not movie_id_text.isdigit():
            self.redirect("/static/poster-placeholder.svg")
            return

        poster_url = self.server.recommender.poster_url(int(movie_id_text))
        self.redirect(poster_url or "/static/poster-placeholder.svg")

    def serve_static(self, request_path: str) -> None:
        relative = request_path.removeprefix("/static/").strip("/")
        target = (STATIC_DIR / relative).resolve()
        static_root = STATIC_DIR.resolve()

        if static_root not in target.parents and target != static_root:
            self.send_json({"error": "Invalid path."}, status=HTTPStatus.BAD_REQUEST)
            return
        if not target.is_file():
            self.send_json({"error": "Static file not found."}, status=HTTPStatus.NOT_FOUND)
            return

        guessed_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        content_type = guessed_type if not guessed_type.startswith("text/") else f"{guessed_type}; charset=utf-8"
        self.serve_file(target, content_type=content_type)

    def serve_file(self, file_path: Path, *, content_type: str) -> None:
        if not file_path.is_file():
            self.send_json({"error": "File not found."}, status=HTTPStatus.NOT_FOUND)
            return

        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location: str, status: HTTPStatus = HTTPStatus.FOUND) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "public, max-age=21600")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the movie recommendation web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind. Default: 127.0.0.1")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on. Default: 8000")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the app automatically in your default browser.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not MOVIE_PATH.exists() or not SIMILARITY_PATH.exists():
        print("movie_list.pkl and similarity.pkl must be in the project folder.", file=sys.stderr)
        return 1

    recommender = MovieRecommender(MOVIE_PATH, SIMILARITY_PATH)
    server = RecommendationHTTPServer((args.host, args.port), MovieRequestHandler, recommender)
    host_for_browser = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{host_for_browser}:{args.port}"

    print(f"Movie recommendation app running at {url}")
    print("Press Ctrl+C to stop the server.")

    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

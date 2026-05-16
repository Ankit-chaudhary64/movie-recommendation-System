const elements = {
  form: document.querySelector("#search-form"),
  input: document.querySelector("#movie-input"),
  suggestions: document.querySelector("#suggestions"),
  randomButton: document.querySelector("#random-button"),
  featuredGrid: document.querySelector("#featured-grid"),
  selectedMovie: document.querySelector("#selected-movie"),
  resultsGrid: document.querySelector("#results-grid"),
  statusBanner: document.querySelector("#status-banner"),
  resultsTitle: document.querySelector("#results-title"),
  resultsCaption: document.querySelector("#results-caption"),
  movieCount: document.querySelector("#movie-count"),
};

let suggestionItems = [];
let activeSuggestionIndex = -1;
let suggestionTimer = null;
let suggestionController = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setBanner(message, type = "info") {
  if (!message) {
    elements.statusBanner.textContent = "";
    elements.statusBanner.className = "status-banner hidden";
    return;
  }

  elements.statusBanner.textContent = message;
  elements.statusBanner.className = `status-banner ${type === "error" ? "error" : ""}`.trim();
}

function setLoading(label) {
  setBanner(label || "Loading recommendations...");
}

function hideSuggestions() {
  suggestionItems = [];
  activeSuggestionIndex = -1;
  elements.suggestions.innerHTML = "";
  elements.suggestions.classList.add("hidden");
}

function renderTags(tags = []) {
  if (!tags.length) {
    return "";
  }

  return `
    <div class="tag-row">
      ${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;
}

function enhancePosterBlock(container) {
  container.querySelectorAll("img[data-poster]").forEach((image) => {
    image.addEventListener(
      "error",
      () => {
        image.src = "/static/poster-placeholder.svg";
      },
      { once: true }
    );
  });
}

function renderPosterCard(movie, showScore = false) {
  return `
    <button class="poster-card" type="button" data-title="${escapeHtml(movie.title)}">
      <span class="poster-art">
        <img data-poster src="${movie.poster}" alt="${escapeHtml(movie.title)} poster" loading="lazy" />
        ${showScore ? `<span class="poster-badge">${movie.score}%</span>` : ""}
      </span>
      <span class="poster-meta">
        <span class="poster-title">${escapeHtml(movie.title)}</span>
        ${showScore ? `<span class="poster-subtitle">#${movie.rank} match</span>` : ""}
      </span>
    </button>
  `;
}

function bindPosterCards(container) {
  container.querySelectorAll("[data-title]").forEach((button) => {
    button.addEventListener("click", () => requestRecommendations(button.dataset.title));
  });
  enhancePosterBlock(container);
}

function renderSelectedMovie(movie, recommendationCount) {
  elements.selectedMovie.classList.remove("empty-state");
  elements.selectedMovie.innerHTML = `
    <div class="spotlight-layout">
      <div class="spotlight-poster">
        <img data-poster src="${movie.poster}" alt="${escapeHtml(movie.title)} poster" loading="lazy" />
      </div>
      <div class="spotlight-copy">
        <p class="section-label">Now showing</p>
        <h1 class="spotlight-title">${escapeHtml(movie.title)}</h1>
        <p class="spotlight-summary">${escapeHtml(movie.summary)}</p>
        ${renderTags(movie.highlights)}
        <div class="spotlight-meta">
          <span>${recommendationCount} matches</span>
          <span>Model based picks</span>
        </div>
      </div>
    </div>
  `;
  enhancePosterBlock(elements.selectedMovie);
}

function renderResults(items) {
  if (!items.length) {
    elements.resultsGrid.innerHTML = "";
    return;
  }

  elements.resultsGrid.innerHTML = items.map((movie) => renderPosterCard(movie, true)).join("");
  bindPosterCards(elements.resultsGrid);
}

function renderFeatured(items) {
  elements.featuredGrid.innerHTML = items.map((movie) => renderPosterCard(movie)).join("");
  bindPosterCards(elements.featuredGrid);
}

function renderSuggestionList(items) {
  suggestionItems = items;
  activeSuggestionIndex = -1;

  if (!items.length) {
    hideSuggestions();
    return;
  }

  elements.suggestions.innerHTML = items
    .map(
      (movie, index) => `
        <button class="suggestion-item" type="button" data-index="${index}">
          ${escapeHtml(movie.title)}
        </button>
      `
    )
    .join("");

  elements.suggestions.classList.remove("hidden");
  elements.suggestions.querySelectorAll("[data-index]").forEach((button) => {
    button.addEventListener("click", () => applySuggestion(Number(button.dataset.index)));
  });
}

function syncActiveSuggestion() {
  elements.suggestions.querySelectorAll(".suggestion-item").forEach((item, index) => {
    item.classList.toggle("active", index === activeSuggestionIndex);
  });
}

function applySuggestion(index) {
  const item = suggestionItems[index];
  if (!item) {
    return;
  }

  elements.input.value = item.title;
  hideSuggestions();
  requestRecommendations(item.title);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || "Request failed.");
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function loadFeatured() {
  const payload = await fetchJson("/api/featured");
  renderFeatured(payload.featured || []);
  if (Array.isArray(payload.featured) && payload.featured.length) {
    requestRecommendations(payload.featured[0].title, { quietBanner: true });
  }
}

async function loadHealth() {
  const payload = await fetchJson("/api/health");
  elements.movieCount.textContent = `${payload.movie_count.toLocaleString()} titles`;
}

async function requestRecommendations(title, options = {}) {
  const movieTitle = (title || "").trim();
  if (!movieTitle) {
    setBanner("Enter a movie title to get recommendations.", "error");
    return;
  }

  hideSuggestions();
  setLoading(`Loading ${movieTitle}...`);
  elements.resultsTitle.textContent = "Recommended";
  elements.resultsCaption.textContent = "Finding close matches...";

  try {
    const payload = await fetchJson(`/api/recommend?movie=${encodeURIComponent(movieTitle)}`);
    elements.input.value = payload.matched_title;
    renderSelectedMovie(payload.movie, payload.recommendations.length);
    renderResults(payload.recommendations || []);
    elements.resultsTitle.textContent = `Because you watched ${payload.matched_title}`;
    elements.resultsCaption.textContent = `${payload.recommendations.length} similar titles`;

    if (!payload.exact_match && payload.matched_title !== payload.requested_title) {
      setBanner(`Showing ${payload.matched_title}`, "info");
    } else if (!options.quietBanner) {
      setBanner("");
    } else {
      setBanner("");
    }
  } catch (error) {
    elements.resultsTitle.textContent = "Recommended";
    elements.resultsCaption.textContent = "Try another title.";
    elements.resultsGrid.innerHTML = "";
    if (error.payload?.suggestions?.length) {
      renderSuggestionList(error.payload.suggestions);
      setBanner(error.message, "error");
    } else {
      hideSuggestions();
      setBanner(error.message || "Unable to fetch recommendations.", "error");
    }
  }
}

async function requestRandomMovie() {
  setLoading("Picking a movie...");
  try {
    const payload = await fetchJson("/api/random");
    elements.input.value = payload.movie.title;
    requestRecommendations(payload.movie.title, { quietBanner: true });
  } catch (error) {
    setBanner(error.message || "Unable to pick a random movie.", "error");
  }
}

async function updateSuggestions() {
  const query = elements.input.value.trim();
  if (!query) {
    hideSuggestions();
    return;
  }

  if (suggestionController) {
    suggestionController.abort();
  }

  suggestionController = new AbortController();

  try {
    const payload = await fetchJson(
      `/api/suggestions?q=${encodeURIComponent(query)}`,
      { signal: suggestionController.signal }
    );
    renderSuggestionList(payload.results || []);
  } catch (error) {
    if (error.name !== "AbortError") {
      hideSuggestions();
    }
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  requestRecommendations(elements.input.value);
});

elements.randomButton.addEventListener("click", () => {
  requestRandomMovie();
});

elements.input.addEventListener("input", () => {
  window.clearTimeout(suggestionTimer);
  suggestionTimer = window.setTimeout(updateSuggestions, 140);
});

elements.input.addEventListener("keydown", (event) => {
  if (!suggestionItems.length) {
    return;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    activeSuggestionIndex = (activeSuggestionIndex + 1) % suggestionItems.length;
    syncActiveSuggestion();
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    activeSuggestionIndex =
      activeSuggestionIndex <= 0 ? suggestionItems.length - 1 : activeSuggestionIndex - 1;
    syncActiveSuggestion();
  }

  if (event.key === "Enter" && activeSuggestionIndex >= 0) {
    event.preventDefault();
    applySuggestion(activeSuggestionIndex);
  }

  if (event.key === "Escape") {
    hideSuggestions();
  }
});

document.addEventListener("click", (event) => {
  if (!elements.form.contains(event.target)) {
    hideSuggestions();
  }
});

Promise.all([loadHealth(), loadFeatured()]).catch((error) => {
  setBanner(error.message || "The app could not load its startup data.", "error");
});

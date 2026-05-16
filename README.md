# Movie Matchmaker

Movie Matchmaker is a content-based movie recommendation system with a browser-based interface. It uses a precomputed similarity matrix to find movies that are most similar to the title selected by the user, then presents the results in a clean streaming-style UI.

This project is a good example of how a machine learning recommendation model can be turned into a complete web application using only Python, HTML, CSS, and JavaScript.

## Overview

The application is built around two serialized model files:

- `movie_list.pkl` stores the movie dataset
- `similarity.pkl` stores similarity scores between all movies

When a user searches for a movie, the app:

1. Finds the movie in the dataset
2. Reads that movie's similarity row from the matrix
3. Sorts the most similar titles
4. Returns the top recommendations in the browser

## Features

- Content-based recommendation engine
- Fast movie search with live suggestions
- Fuzzy title matching for spelling mistakes
- Dark streaming-style frontend
- Poster-first recommendation cards
- Random movie picker
- Lightweight Python server using the standard library

## Tech Stack

- Python
- `pandas`
- `numpy`
- Built-in `http.server`
- HTML
- CSS
- JavaScript

## Project Structure

```text
girigo/
├── app.py
├── movie_list.pkl
├── similarity.pkl
├── README.md
└── static/
    ├── app.js
    ├── index.html
    ├── poster-placeholder.svg
    └── styles.css
```

## Dataset and Model Files

### `movie_list.pkl`

This file contains the movie catalog and includes:

- `movie_id`
- `title`
- `tags`

### `similarity.pkl`

This file contains the precomputed similarity matrix used to generate recommendations.

Important:

- `similarity.pkl` is large, around 185 MB
- standard GitHub uploads do not allow files larger than 100 MB
- if you plan to push this repository to GitHub, use Git LFS or store the model files separately

## Installation

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd girigo
```

### 2. Install dependencies

```bash
pip install pandas numpy
```

### 3. Make sure the model files are present

The following files must exist in the project root:

- `movie_list.pkl`
- `similarity.pkl`

## Running the Application

Start the server with:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8000
```

To open the browser automatically:

```bash
python app.py --open-browser
```

## How to Use

1. Open the app in your browser
2. Search for a movie title such as `Avatar` or `Interstellar`
3. Select a movie from the suggestions or submit the search
4. View the recommended movies returned by the similarity model
5. Click any recommended movie to continue exploring related titles

## API Endpoints

The project also exposes simple backend endpoints:

- `/` - main application page
- `/api/health` - basic server and dataset status
- `/api/featured` - featured movie list
- `/api/random` - random movie selection
- `/api/suggestions?q=avatar` - title suggestions
- `/api/recommend?movie=Avatar` - recommendations for a selected movie
- `/api/poster/<movie_id>` - poster redirect or local placeholder

## Frontend Highlights

The frontend is designed to feel closer to a modern streaming platform than a default dashboard. It includes:

- a dark cinematic layout
- simplified navigation
- poster-based movie rows
- a spotlight section for the selected movie
- responsive behavior for desktop and mobile screens

## Poster Support

Movie posters are resolved using the movie ID and loaded dynamically when available. If a poster cannot be found, the application falls back to a local placeholder image.

Note:

- poster loading may require internet access
- recommendations still work locally even if poster loading fails

## Limitations

- recommendations depend entirely on the uploaded model files
- the system is content-based, so it does not learn from real user behavior
- poster data is not stored directly in the dataset
- large model files may make GitHub publishing harder without Git LFS

## Future Improvements

- add genre, rating, and release year filters
- integrate a proper movie metadata API
- show more recommendation categories
- add user watchlists or favorites
- deploy the app online

## Why This Project Matters

This project demonstrates the full pipeline from machine learning output to end-user product:

- preparing recommendation data
- serving model results through a backend
- designing a usable frontend
- packaging the solution as a real web application

It is suitable for:

- machine learning mini-projects
- recommendation system demos
- academic submissions
- portfolio projects

## Author

Built as a movie recommendation system project using a precomputed similarity model and a custom browser-based interface.

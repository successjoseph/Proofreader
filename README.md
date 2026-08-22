# Proofreader (AI Auto-Editor)

![Language](https://img.shields.io/badge/language-Python%20%2F%20HTML%2FJS-blue)

## Table of Contents
- [About](#about)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Contributing](#contributing)
- [Authors and License](#authors-and-license)

## About

Proofreader ("AI Auto-Editor") is a single-page manuscript editor for writers. The frontend (`index.html`) is a self-contained dark-themed editor with a library/book/chapter sidebar, an inline word-by-word editable text area, an undo/redo change log, and an AI feedback panel. It authenticates users with Firebase Authentication (email/password) and stores books, chapters, and edit history in Firestore. A small Flask backend (`app.py`) provides two AI-powered endpoints backed by Groq's hosted LLM (`meta-llama/llama-4-scout-17b-16e-instruct`) — one to suggest synonyms for a double-clicked word, and one to produce an editorial critique of the current chapter — plus a `.docx` export endpoint built with `python-docx`. The project is configured (`vercel.json`) to deploy as a Vercel app: the backend as a Python serverless function and `index.html` as a static asset. This reads as a personal writing tool built for the author's own manuscript-editing workflow rather than a general-purpose product.

## Prerequisites
- Python 3.x
- A Groq API key (for the AI endpoints)
- A Firebase project with Email/Password Authentication and Firestore enabled (the client config is already hardcoded in `index.html`, project `prasst-1`)

## Installation
```bash
git clone https://github.com/successjoseph/Proofreader.git
cd Proofreader
pip install -r requirements.txt
```
`requirements.txt` pins: `Flask==3.0.0`, `flask-cors==4.0.0`, `groq==0.4.2`, `httpx==0.27.2`, `python-docx==1.1.0`, `python-dotenv==1.0.1`.

## Configuration
Create a `.env` file (already excluded via `.gitignore`) in the project root with:
```
GROQ_API_KEY=your_groq_api_key_here
```
If `GROQ_API_KEY` is missing, the Groq client is never initialized and the AI endpoints will fail. The Firebase web config (apiKey, authDomain, projectId, etc.) is embedded directly in `index.html` — this is standard for Firebase client SDKs and is not a secret, but it does mean the app is tied to that specific Firebase project.

## Usage
Run the Flask backend locally:
```bash
python app.py
```
This starts a dev server on port 5000. Since `vercel.json` routes `/(.*)` to `index.html` and `/api/(.*)`/`/export` to `app.py`, in production (or via `vercel dev`) both are served together; for local testing you may need to open `index.html` directly or serve it alongside the Flask app.

In the app: log in with a Firebase email/password account, create or select a "book," add chapters, edit text inline, double-click any word to fetch AI synonym suggestions, click "AI Review" to get an editorial critique in the feedback panel, and use "Export .docx" to download the manuscript.

## API Documentation
- `POST /api/ai/synonyms` — body `{ "word": str, "context": str }` → returns a JSON array of 3 synonym strings (via Groq).
- `POST /api/ai/critique` — body `{ "text": str, "history": [...] }` → returns `{ "critique": "<markdown text>" }`, an editorial critique with suggested "Change X to Y" snippets.
- `POST /export` — body `{ "chapters": [{ "title": str, "content": str }, ...] }` → returns a generated `Manuscript.docx` file download.

## Testing
No automated tests are currently included.

## Contributing
This is a personal writing-tool project; these notes are primarily for the author's own future reference rather than an open call for contributions.

## Authors and License
**Author:** [successjoseph](https://github.com/successjoseph)
No license file included in this repository — all rights reserved by default.

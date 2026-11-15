import os
import io
import re
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from groq import Groq
from docx import Document
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

MODEL = "openai/gpt-oss-20b"
MAX_CRITIQUE_CHARS = 24000  # gpt-oss-20b has a large context window, so most chapters fit whole
MAX_HISTORY_MESSAGES = 6    # only the most recent turns are sent back as context
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def ask_model(messages):
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not set on the server.")
    response = client.chat.completions.create(model=MODEL, messages=messages)
    return (response.choices[0].message.content or "").strip()


# Serves the editor when running locally with `python app.py` (on Vercel, index.html is served statically)
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


# ai_synonyms route
@app.route('/api/ai/synonyms', methods=['POST'])
def ai_synonyms():
    data = request.get_json(silent=True) or {}
    word = (data.get('word') or '').strip()
    context = (data.get('context') or '').strip()
    if not word:
        return jsonify({"error": "No word was sent."}), 400

    prompt = (f"Give me 3 synonyms for the word '{word}' suitable for this context: '{context}'. "
              "Return only the words separated by commas.")
    try:
        synonyms_text = ask_model([{"role": "user", "content": prompt}])
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    # models sometimes number, bullet or quote the words, so clean each one up
    synonyms = []
    for s in re.split(r'[,\n]', synonyms_text):
        s = re.sub(r'^\s*(\d+[.)]|[-*•])\s*', '', s).strip().strip('"\'.*').strip()
        if s and s.lower() != word.lower() and s.lower() not in (x.lower() for x in synonyms):
            synonyms.append(s)
    return jsonify(synonyms[:3])

# ai_critique route
@app.route('/api/ai/critique', methods=['POST'])
def ai_critique():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    history = data.get('history') or []  # pull context history
    if not text:
        return jsonify({"error": "The chapter is empty. Add some text first."}), 400
    if not isinstance(history, list):
        history = []

    system_prompt = """You are an expert editor. Analyze the chapter text for flaws, inconsistencies, and pacing. 
    Format your response in Markdown. At the end, you MUST provide actionable snippets in this exact format:
    **Suggested Snippets:**
    * Change "[old text]" to "[new text]" """

    messages = [{"role": "system", "content": system_prompt}]

    # append recent chat history for context, keeping only well formed user/assistant turns
    for msg in history[-MAX_HISTORY_MESSAGES:]:
        if isinstance(msg, dict) and msg.get('role') in ('user', 'assistant') and isinstance(msg.get('content'), str) and msg['content']:
            messages.append({"role": msg['role'], "content": msg['content']})

    if len(text) > MAX_CRITIQUE_CHARS:
        text = text[:MAX_CRITIQUE_CHARS] + "\n\n[The chapter continues, but was cut off here.]"
    messages.append({"role": "user", "content": f"Text to analyze: {text}"})

    try:
        critique = ask_model(messages)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    if not critique:
        return jsonify({"error": "The model returned an empty answer. Try again."}), 502
    return jsonify({"critique": critique})

@app.route('/export', methods=['POST'])
def export_docx():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip() or 'Manuscript Export'
    doc = Document()
    doc.add_heading(title, 0)

    for i, chap in enumerate(data.get('chapters') or []):
        if i > 0:
            doc.add_page_break()
        doc.add_heading(chap.get('title') or 'Untitled', level=1)
        # one Word paragraph per line, so the manuscript keeps its paragraph breaks
        for para in (chap.get('content') or '').split('\n'):
            if para.strip():
                doc.add_paragraph(para.strip())

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    filename = re.sub(r'[^\w\- ]', '', title).strip() or 'Manuscript'
    return send_file(
        file_stream,
        as_attachment=True,
        download_name=f'{filename}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)

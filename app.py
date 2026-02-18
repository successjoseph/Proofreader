import os
import json
import glob
from functools import wraps
from flask import Flask, request, Response, session, render_template_string, jsonify, send_file
import google.generativeai as genai
from docx import Document

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = 'super_secret_nymo_key_change_in_prod'

# 🎁 Hardwired Creds
USERS = {
    "nymo": "password",
    "editor2": "1234"
}

# 🎁 AI Configuration (Set this in your .env)
# export GEMINI_API_KEY="your_api_key_here"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')

# Storage Paths
DATA_DIR = 'chapters'
os.makedirs(DATA_DIR, exist_ok=True)

# --- AUTH DECORATOR ---
def check_auth(username, password):
    return username in USERS and USERS[username] == password

def authenticate():
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- BACKEND LOGIC ---

def get_chapter_files():
    """Returns a sorted list of chapter IDs based on files present."""
    files = glob.glob(os.path.join(DATA_DIR, 'chapter_*.txt'))
    ids = []
    for f in files:
        try:
            # Extract ID from filename "chapter_1.txt"
            base = os.path.basename(f)
            cid = int(base.replace('chapter_', '').replace('.txt', ''))
            ids.append(cid)
        except:
            pass
    return sorted(ids)

def apply_changes_to_text(original_text, changes):
    """
    Reconstructs text based on JSON changes.
    Index logic: Text is split by space. We replace indices found in 'changes'.
    """
    words = original_text.split(' ')
    
    # Create a map of index -> new_word
    change_map = {c['word_index']: c['new_word'] for c in changes if c.get('status') != 'rejected'}
    
    final_words = []
    for i, word in enumerate(words):
        if str(i) in change_map or i in change_map:
            final_words.append(change_map.get(str(i)) or change_map.get(i))
        else:
            final_words.append(word)
            
    return " ".join(final_words)

# --- ROUTES ---

@app.route('/')
@requires_auth
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/chapters', methods=['GET'])
@requires_auth
def list_chapters_route():
    ids = get_chapter_files()
    return jsonify(ids)

@app.route('/api/chapter/<int:chapter_id>', methods=['GET', 'POST'])
@requires_auth
def handle_chapter(chapter_id):
    txt_path = os.path.join(DATA_DIR, f'chapter_{chapter_id}.txt')
    json_path = os.path.join(DATA_DIR, f'chapter_{chapter_id}.json')

    if request.method == 'POST':
        # 🎁 Copy-paste per chapter / Save
        data = request.json
        content = data.get('content')
        title = data.get('title', f'Chapter {chapter_id}')
        changes = data.get('changes', [])
        
        # Save raw text
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 🎁 Store changes as serialized persistent JSON storage
        meta = {
            'chapter_id': chapter_id,
            'title': title,
            'changes': changes,
            'word_count': len(content.split())
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)
            
        return jsonify({"status": "saved", "word_count": meta['word_count']})

    else:
        # GET
        if not os.path.exists(txt_path):
            return jsonify({"exists": False})
        
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        meta = {}
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                
        return jsonify({
            "exists": True,
            "content": content,
            "title": meta.get('title', ''),
            "changes": meta.get('changes', [])
        })

@app.route('/api/ai/synonyms', methods=['POST'])
@requires_auth
def ai_synonyms():
    data = request.json
    word = data.get('word')
    context = data.get('context') # Sentence surrounding the word
    
    if not GEMINI_API_KEY:
        return jsonify(["AI Not Configured", "Check .env", "Error"])

    prompt = f"Give me 3 synonyms for the word '{word}' suitable for this context: '{context}'. Return only the words separated by commas."
    try:
        response = model.generate_content(prompt)
        synonyms = [s.strip() for s in response.text.split(',')]
        return jsonify(synonyms)
    except Exception as e:
        return jsonify(["Error fetching synonyms"])

@app.route('/api/ai/critique', methods=['POST'])
@requires_auth
def ai_critique():
    # 🎁 Feedback on general writing method and inconsistencies
    text = request.json.get('text')
    
    if not GEMINI_API_KEY:
        return jsonify({"critique": "AI API Key missing."})

    prompt = f"Analyze the following chapter text. Identify writing flaws, inconsistencies, and pacing issues. Be concise and constructive.\n\nText: {text[:4000]}..." # Limit context if needed
    try:
        response = model.generate_content(prompt)
        return jsonify({"critique": response.text})
    except Exception as e:
        return jsonify({"critique": str(e)})

@app.route('/export', methods=['GET'])
@requires_auth
def export_docx():
    # 🎁 Make word document with proper headings
    doc = Document()
    doc.add_heading('Manuscript Export', 0)

    ids = get_chapter_files()
    if not ids:
        return "No chapters found."

    for cid in ids:
        txt_path = os.path.join(DATA_DIR, f'chapter_{cid}.txt')
        json_path = os.path.join(DATA_DIR, f'chapter_{cid}.json')
        
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            
            title = f"Chapter {cid}"
            changes = []
            
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    title = meta.get('title', title)
                    changes = meta.get('changes', [])

            # Apply logic to create clean text
            final_text = apply_changes_to_text(raw_text, changes)
            
            doc.add_heading(title, level=1)
            doc.add_paragraph(final_text)
            doc.add_page_break()

    output_path = 'Manuscript.docx'
    doc.save(output_path)
    return send_file(output_path, as_attachment=True)

# --- FRONTEND TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Auto-Editor</title>
    <style>
        :root { --bg: #1a1a1a; --fg: #e0e0e0; --accent: #00adb5; --del: #ff6b6b; --add: #6bff6b; }
        body { font-family: 'Courier New', monospace; background: var(--bg); color: var(--fg); margin: 0; display: flex; height: 100vh; }
        
        /* Layout */
        #sidebar { width: 250px; border-right: 1px solid #333; padding: 20px; display: flex; flex-direction: column; }
        #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        #toolbar { padding: 10px 20px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; background: #252525; }
        #editor-container { flex: 1; overflow-y: auto; padding: 40px; line-height: 1.8; font-size: 1.1em; white-space: pre-wrap; }
        #feedback-panel { height: 150px; border-top: 1px solid #333; padding: 20px; overflow-y: auto; background: #222; font-size: 0.9em; }

        /* Components */
        .chapter-btn { display: block; width: 100%; padding: 10px; margin-bottom: 5px; background: #333; color: #fff; border: none; cursor: pointer; text-align: left; }
        .chapter-btn.active { background: var(--accent); color: #000; }
        button { background: var(--accent); border: none; padding: 8px 16px; color: #000; font-weight: bold; cursor: pointer; border-radius: 4px; }
        button:hover { opacity: 0.9; }
        input { background: #333; border: 1px solid #444; color: #fff; padding: 5px; width: 200px; }

        /* 🎁 Indexing & Highlights */
        span.word { cursor: pointer; padding: 0 1px; border-radius: 2px; transition: background 0.2s; }
        span.word:hover { background: #333; }
        span.changed-word { background: rgba(0, 173, 181, 0.2); border-bottom: 2px solid var(--accent); }
        
        /* Modal */
        #synonym-modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #333; padding: 20px; border: 1px solid var(--accent); display: none; z-index: 100; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .syn-option { display: block; width: 100%; padding: 10px; background: #444; margin-bottom: 5px; border: none; color: #fff; cursor: pointer; }
        .syn-option:hover { background: var(--accent); color: #000; }

        /* Helper Classes */
        .loading { opacity: 0.5; pointer-events: none; }
    </style>
</head>
<body>

<div id="sidebar">
    <h3>📖 Chapters</h3>
    <div id="chapter-list"></div>
    <button onclick="createNewChapter()" style="margin-top: 10px;">+ New Chapter</button>
    <div style="margin-top: auto;">
        <p id="word-counter">Words: 0</p>
        <a href="/export" target="_blank"><button style="width:100%">Export .docx</button></a>
    </div>
</div>

<div id="main">
    <div id="toolbar">
        <div>
            <input type="text" id="chapter-title" placeholder="Chapter Title">
        </div>
        <div>
            <button onclick="undo()">↶ Undo</button>
            <button onclick="redo()">↷ Redo</button>
            <button onclick="getAICritique()">🤖 AI Review</button>
            <button onclick="saveChapter()">💾 Save</button>
        </div>
    </div>
    
    <div id="editor-container">
        <div id="editor" contenteditable="true">Wait...</div>
    </div>

    <div id="feedback-panel">
        <strong>AI Feedback:</strong> <span id="ai-output">No analysis yet.</span>
    </div>
</div>

<div id="synonym-modal">
    <h4>Select Replacement</h4>
    <div id="synonym-list"></div>
    <button onclick="closeModal()" style="margin-top: 10px; background: #555; color: #fff;">Cancel</button>
</div>

<script>
    let currentChapterId = 1;
    let originalText = "";
    let wordsArray = [];
    let changes = []; // { word_index: int, old: str, new_word: str, type: str }
    
    // 🎁 Undo/Redo Cache
    let undoStack = [];
    let redoStack = [];

    document.addEventListener('DOMContentLoaded', () => {
        loadChapterList();
        loadChapter(1);
    });

    // --- CHAPTER LOGIC ---

    async function loadChapterList() {
        const res = await fetch('/api/chapters');
        const ids = await res.json();
        const list = document.getElementById('chapter-list');
        list.innerHTML = '';
        ids.forEach(id => {
            const btn = document.createElement('button');
            btn.className = `chapter-btn ${id === currentChapterId ? 'active' : ''}`;
            btn.innerText = `Chapter ${id}`;
            btn.onclick = () => loadChapter(id);
            list.appendChild(btn);
        });
        if(ids.length === 0) createNewChapter();
    }

    async function createNewChapter() {
        const res = await fetch('/api/chapters');
        const ids = await res.json();
        const newId = ids.length > 0 ? Math.max(...ids) + 1 : 1;
        currentChapterId = newId;
        originalText = "";
        wordsArray = [];
        changes = [];
        renderEditor();
        document.getElementById('chapter-title').value = `Chapter ${newId}`;
        loadChapterList();
    }

    async function loadChapter(id) {
        currentChapterId = id;
        document.querySelectorAll('.chapter-btn').forEach(b => b.classList.remove('active'));
        // Re-highlight active (simplified)
        
        const res = await fetch(`/api/chapter/${id}`);
        const data = await res.json();
        
        if (data.exists) {
            originalText = data.content;
            changes = data.changes || [];
            document.getElementById('chapter-title').value = data.title;
        } else {
            originalText = "Paste your chapter content here...";
            changes = [];
        }
        
        wordsArray = originalText.split(' '); // 🎁 Naive index splitting
        renderEditor();
    }

    async function saveChapter() {
        // We save the RAW text (originalText) and the changes JSON
        // If user edited text manually (typed), we assume originalText matches editor current innerText for MVP simplicity
        // But to keep indexing, we prefer selecting words. 
        // For this demo, we save the text as-is if no changes, or handle it carefully.
        
        const payload = {
            content: originalText, // Keeps base stable
            changes: changes,
            title: document.getElementById('chapter-title').value
        };

        const res = await fetch(`/api/chapter/${currentChapterId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const status = await res.json();
        alert('Chapter Saved. Word Count: ' + status.word_count);
        loadChapterList();
    }

    // --- EDITOR & INDEXING ---

    function renderEditor() {
        const editor = document.getElementById('editor');
        editor.innerHTML = '';
        
        // 🎁 Index each word
        wordsArray.forEach((word, index) => {
            const span = document.createElement('span');
            span.className = 'word';
            span.dataset.index = index;
            span.id = `w-${index}`;
            
            // Check if modified
            const change = changes.find(c => c.word_index === index);
            if (change) {
                span.innerText = change.new_word + ' ';
                span.classList.add('changed-word');
                span.title = `Original: ${change.original_word}`;
            } else {
                span.innerText = word + ' ';
            }
            
            // 🎁 Synonym suggestions on double tap
            span.ondblclick = (e) => handleDoubleTap(e, index, word);
            
            editor.appendChild(span);
        });
        
        document.getElementById('word-counter').innerText = `Words: ${wordsArray.length}`;
    }
    
    // --- SYNONYMS & CHANGES ---

    let selectedWordIndex = null;

    async function handleDoubleTap(e, index, word) {
        e.preventDefault();
        selectedWordIndex = index;
        
        // Get context (prev 5 words + word + next 5 words)
        const start = Math.max(0, index - 5);
        const end = Math.min(wordsArray.length, index + 5);
        const context = wordsArray.slice(start, end).join(' ');

        const modal = document.getElementById('synonym-modal');
        const list = document.getElementById('synonym-list');
        list.innerHTML = 'Loading AI suggestions...';
        modal.style.display = 'block';

        const res = await fetch('/api/ai/synonyms', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ word: word, context: context })
        });
        
        const synonyms = await res.json();
        list.innerHTML = '';
        synonyms.forEach(syn => {
            const btn = document.createElement('button');
            btn.className = 'syn-option';
            btn.innerText = syn;
            btn.onclick = () => applyChange(index, word, syn, 'synonym');
            list.appendChild(btn);
        });
    }

    function closeModal() {
        document.getElementById('synonym-modal').style.display = 'none';
    }

    function applyChange(index, oldWord, newWord, type) {
        // Push to Undo Stack
        undoStack.push({ type: 'add', change: { word_index: index, original_word: oldWord, new_word: newWord, type: type }});
        redoStack = []; // Clear redo
        
        // Update State
        // Remove existing change for this index if exists
        changes = changes.filter(c => c.word_index !== index);
        changes.push({ word_index: index, original_word: oldWord, new_word: newWord, error_type: type, status: 'accepted' });
        
        closeModal();
        renderEditor();
    }

    // --- UNDO / REDO ---

    function undo() {
        if (undoStack.length === 0) return;
        const action = undoStack.pop();
        
        if (action.type === 'add') {
            // Revert the add
            const changeToRemove = action.change;
            changes = changes.filter(c => c.word_index !== changeToRemove.word_index);
            redoStack.push(action);
        }
        renderEditor();
    }

    function redo() {
        if (redoStack.length === 0) return;
        const action = redoStack.pop();
        
        if (action.type === 'add') {
            changes.push(action.change);
            undoStack.push(action);
        }
        renderEditor();
    }

    // --- AI CRITIQUE ---

    async function getAICritique() {
        const btn = document.querySelector('#toolbar button:nth-child(3)');
        btn.innerText = "Analyzing...";
        
        // Construct current text
        const currentText = document.getElementById('editor').innerText;
        
        const res = await fetch('/api/ai/critique', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text: currentText })
        });
        
        const data = await res.json();
        document.getElementById('ai-output').innerText = data.critique;
        btn.innerText = "🤖 AI Review";
    }

    // Handle Paste to update Original Text (First time only for chapter)
    document.getElementById('editor').addEventListener('input', (e) => {
        // Simple handler to catch paste events if empty
        if (wordsArray.length <= 1) {
            originalText = e.target.innerText;
            wordsArray = originalText.split(' ');
            renderEditor();
        }
    });

</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True, port=5000)

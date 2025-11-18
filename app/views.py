from app import app
from flask import render_template, request, redirect
import requests
import json
connected_node_address = "http://127.0.0.1:8000"
posts = []

def fetch_posts():
    global posts
    response = requests.get(f"{connected_node_address}/chain")
    if response.status_code == 200:
        content = []
        chain = json.loads(response.content)
        for block in chain["chain"]:
            for tx in block["transactions"]:
                tx["index"] = block["index"]
                tx["hash"] = block["previous_hash"]
                content.append(tx)
        posts = sorted(content, key=lambda k: k['timestamp'], reverse=True)

@app.route('/')
@app.route('/index')
def index():
    fetch_posts()
    return render_template('index.html',
                           title='Blockchain Web',
                           posts=posts)

@app.route('/submit', methods=['POST'])
def submit_textarea():
    author = request.form["author"]
    content = request.form["content"]

    post_object = {
        "author": author,
        "content": content
    }

    new_tx_address = f"{connected_node_address}/new_transaction"
    requests.post(new_tx_address, json=post_object)

    return redirect('/')

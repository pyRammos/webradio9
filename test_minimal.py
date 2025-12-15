#!/usr/bin/env python3
import sys
sys.path.append('/home/george/projects/radio1')

from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello World"

if __name__ == '__main__':
    print("Starting minimal Flask app...")
    app.run(host='0.0.0.0', port=5000, debug=False)

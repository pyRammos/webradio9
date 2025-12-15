#!/usr/bin/env python3
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Ultra Minimal Web Service Running"

if __name__ == '__main__':
    print("Starting ultra minimal web service...")
    app.run(host='0.0.0.0', port=5000, debug=False)

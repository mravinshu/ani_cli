from flask_cors import CORS
from flask import Flask, render_template, request, redirect

app = Flask(__name__)
CORS(app)
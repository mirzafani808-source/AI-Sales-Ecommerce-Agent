import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import app as appmod
print('GOOGLE_CLIENT_ID', os.environ.get('GOOGLE_CLIENT_ID'))
print('GOOGLE_CLIENT_SECRET', os.environ.get('GOOGLE_CLIENT_SECRET'))
print('google obj', appmod.google)
print('github obj', appmod.github)
print('blueprints', list(appmod.app.blueprints.keys()))

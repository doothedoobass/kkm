import os

# 1. Create the missing static folder to fix the warning
os.makedirs("static", exist_ok=True)

# 2. Create the missing wsgi.py file to fix the crash
wsgi_content = """import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'neuralspace.settings')
application = get_wsgi_application()
"""

with open("neuralspace/wsgi.py", "w", encoding="utf-8") as f:
    f.write(wsgi_content)

print("Patch applied! The server is ready.")
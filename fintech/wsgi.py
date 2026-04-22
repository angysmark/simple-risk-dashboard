"""
WSGI config for fintech project.

Exposes the WSGI callable as a module-level variable named ``application``.
For production deployment with gunicorn:
    gunicorn fintech.wsgi:application
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fintech.settings")

application = get_wsgi_application()

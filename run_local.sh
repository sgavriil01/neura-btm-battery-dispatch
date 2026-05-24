#!/usr/bin/env bash
set -e

python manage.py migrate
python manage.py seed_week_data
python manage.py run_dispatch
python manage.py runserver

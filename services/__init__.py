"""Service layer: read models and analytics.

Everything here is pure and testable: functions take a DB connection (or plain
row mappings) and return dictionaries/values. No Flask objects, no request
context - the HTTP layer (app.py, web/pages.py) is a thin presentation shell
over these functions.
"""

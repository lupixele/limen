@echo off
echo Starting Limen Autonomous Agent on http://127.0.0.1:8000 ...
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause

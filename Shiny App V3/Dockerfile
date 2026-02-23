# Shiny App V3 – MBTA Red Line Tracker with AI Commuter Report
# Deploy to DigitalOcean App Platform or similar. Run: docker build -t redline-v3 .

FROM python:3.12-slim

RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /home/app
RUN chown app:app -R /home/app
USER app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY app.py .
COPY api/ api/
COPY ai_reporter/ ai_reporter/
COPY ui/ ui/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

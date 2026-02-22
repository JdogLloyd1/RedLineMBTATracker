# Shiny App V2 – MBTA Red Line Tracker with AI Commuter Report
# Deploy to DigitalOcean App Platform or similar. Run: docker build -t redline-v2 .

FROM python:3.12-slim

# Non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /home/app
RUN chown app:app -R /home/app
USER app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy app
COPY app.py .
COPY api/ api/
COPY ai_reporter/ ai_reporter/
COPY ui/ ui/

# Expose port for Uvicorn (Shiny uses Uvicorn)
EXPOSE 8000

# Run Shiny app via Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

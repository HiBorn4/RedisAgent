FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create streamlit config directory
RUN mkdir -p .streamlit

# Write streamlit config (disable telemetry, set server settings)
RUN echo '[server]\nheadless = true\nport = 8501\nenableCORS = false\n\n[browser]\ngatherUsageStats = false' > .streamlit/config.toml

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]

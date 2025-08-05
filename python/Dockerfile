FROM python:3.12-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.7.1

# Copy Poetry configuration from parent directory
COPY ../pyproject.toml ../poetry.lock* ./

# Configure Poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev

# Copy only Python application code
COPY . .

# Expose port
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
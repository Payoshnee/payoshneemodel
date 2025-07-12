# Use official Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy code and config
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Environment vars (can be overridden in runtime)
ENV OPENAI_API_KEY=""
ENV GITHUB_TOKEN=""

# Run the bot
CMD ["python", "review_bot.py"]

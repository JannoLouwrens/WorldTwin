FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the worldtwin package
COPY worldtwin ./worldtwin

RUN mkdir -p /cache /cache/v1

EXPOSE 8090

# Run as: python -m worldtwin
CMD ["python", "-u", "-m", "worldtwin"]

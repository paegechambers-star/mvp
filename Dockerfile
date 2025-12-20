FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install -e . \
    && pip install fastapi "uvicorn[standard]" typer pydantic pydantic-settings sqlmodel
EXPOSE 8000
CMD ["uvicorn","frapp.api:app","--host","0.0.0.0","--port","8000"]

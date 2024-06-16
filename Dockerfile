ARG SERVER_HOST
ARG SERVER_PORT

FROM python:3.10

ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -e .

CMD python3 enhancifai_backend/run_enhancifai.py

EXPOSE ${SERVER_PORT}

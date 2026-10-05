# --- build RTKLIB (rtklibexplorer demo5) console solver ---
FROM python:3.11-slim AS rtklib
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch demo5 https://github.com/rtklibexplorer/RTKLIB.git /src/RTKLIB \
    && make -C /src/RTKLIB/app/consapp/rnx2rtkp/gcc

# --- runtime ---
FROM python:3.11-slim
COPY --from=rtklib /src/RTKLIB/app/consapp/rnx2rtkp/gcc/rnx2rtkp /usr/local/bin/rnx2rtkp
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV GNSS_WORK_ROOT=/app/data/jobs GNSS_PRODUCT_CACHE=/app/data/products
EXPOSE 8000
CMD ["uvicorn", "gnss_pipeline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# KX-Tab TabPy container (Azure Container Apps or any container host). HTTP on 8000; the host
# terminates HTTPS. Env: KXTAB_TICKER, KXTAB_TABPY_PASSWORD, optional KXTAB_TABPY_USER and KXTAB_*.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt requirements-tabpy.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-tabpy.txt

COPY kxtab ./kxtab
COPY deploy/appservice ./deploy/appservice

RUN useradd --system --no-create-home kxtab
USER kxtab
EXPOSE 8000
CMD ["bash", "deploy/appservice/startup.sh"]

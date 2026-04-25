FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1

COPY functions/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY functions/ /home/site/wwwroot/
COPY training/ /home/site/wwwroot/training/

WORKDIR /home/site/wwwroot

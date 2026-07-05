ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages paho-mqtt requests

COPY eufy2ha /app/eufy2ha
COPY run.sh /
RUN chmod a+x /run.sh
WORKDIR /app
CMD [ "/run.sh" ]

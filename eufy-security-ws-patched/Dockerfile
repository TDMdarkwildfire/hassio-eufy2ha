ARG BUILD_FROM
FROM $BUILD_FROM

ARG EUFY_SECURITY_WS_REF=push-message-event

WORKDIR /usr/src/app
RUN \
    set -x \
    # The Alpine 3.23 base image (see build.yaml) ships Node.js 24 in its main
    # repository, so nodejs/npm install directly with no edge-repo workarounds.
    && apk add --no-cache \
        git \
        jq \
        nodejs \
        npm \
    && node --version \
    # Fail the build if the base ever regresses below Node 24.
    && case "$(node --version)" in v24.*) ;; *) echo "Expected Node 24, got $(node --version)" >&2; exit 1 ;; esac \
    # Install the patched fork (adds the "push message" driver event). The
    # fork's package.json has a prepare script, so npm builds dist/ on install
    # and the package lands under the same path bropat's run.sh expects.
    && npm install --force \
    "git+https://github.com/TDMdarkwildfire/eufy-security-ws.git#${EUFY_SECURITY_WS_REF}" \
    && test -f node_modules/eufy-security-ws/dist/bin/server.js \
    && grep -q "push message" node_modules/eufy-security-ws/dist/lib/forward.js \
    && apk del git \
    && npm cache clean --force

COPY run.sh /
RUN chmod a+x /run.sh
WORKDIR /data

CMD [ "/run.sh" ]

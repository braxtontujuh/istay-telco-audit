ARG POSTGRES_IMAGE=postgres:17-alpine
FROM ${POSTGRES_IMAGE}
COPY *.sh /opt/backup/
RUN chmod 0555 /opt/backup/*.sh
ENTRYPOINT ["sh", "/opt/backup/schedule.sh"]

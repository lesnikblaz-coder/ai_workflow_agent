FROM ubuntu:latest
LABEL authors="Blaz"

ENTRYPOINT ["top", "-b"]
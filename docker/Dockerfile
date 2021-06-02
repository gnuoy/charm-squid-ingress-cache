
FROM ubuntu:focal

ENV DEBIAN_FRONTEND noninteractive

RUN apt update \
    && apt dist-upgrade --yes

RUN apt install --assume-yes --option=Dpkg::Options::=--force-confold squid

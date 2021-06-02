#!/usr/bin/env python3
# Copyright 2021 liam
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus
from charms.nginx_ingress_integrator.v0.ingress import (
    IngressRequires,
)
from charms.squid_ingress_proxy.v0.ingress_proxy import (
    IngressProxyProvides,
)
from charms.squid_ingress_cache.v0.ingress_cache import (
    IngressCacheProvides,
)
import jinja2

# from ops.framework import EventBase, EventSource, Object
# from ops.charm import CharmEvents

logger = logging.getLogger(__name__)

SQUID_TEMPLATE = """
acl localnet src 0.0.0.1-0.255.255.255	# RFC 1122 "this" network (LAN)
acl localnet src 10.0.0.0/8		# RFC 1918 local private network (LAN)
acl localnet src 100.64.0.0/10		# RFC 6598 shared address space (CGN)
acl localnet src 169.254.0.0/16 	# RFC 3927 link-local (directly plugged) machines
acl localnet src 172.16.0.0/12		# RFC 1918 local private network (LAN)
acl localnet src 192.168.0.0/16		# RFC 1918 local private network (LAN)
acl localnet src fc00::/7       	# RFC 4193 local private network range
acl localnet src fe80::/10      	# RFC 4291 link-local (directly plugged) machines
acl SSL_ports port 443
acl Safe_ports port 80		# http
acl Safe_ports port 21		# ftp
acl Safe_ports port 443		# https
acl Safe_ports port 70		# gopher
acl Safe_ports port 210		# wais
acl Safe_ports port 1025-65535	# unregistered ports
acl Safe_ports port 280		# http-mgmt
acl Safe_ports port 488		# gss-http
acl Safe_ports port 591		# filemaker
acl Safe_ports port 777		# multiling http
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow localhost manager
http_access deny manager
include /etc/squid/conf.d/*
http_access allow localhost
http_access allow localnet
http_access deny all
coredump_dir /var/spool/squid
{% if refresh_patterns -%}
{% for refresh_pattern in refresh_patterns -%}
{% if refresh_pattern.case_sensitive -%}
refresh_pattern -i {{ refresh_pattern.regex }} {{ refresh_pattern.min }} {{ refresh_pattern.percent }}% {{ refresh_pattern.max }} {{ refresh_pattern.options|join(' ') }}
{% else %}
refresh_pattern {{ refresh_pattern.regex }} {{ refresh_pattern.min }} {{ refresh_pattern.percent }}% {{ refresh_pattern.max }} {{ refresh_pattern.options|join(' ') }}
{% endif %}
{% endfor -%}
{% endif %}
refresh_pattern . 0 20% 4320
{% if port %}
http_port {{ port }} accel
{% for peer in peers -%}
cache_peer {{ peer }} parent {{ port }} 0 no-query originserver
{% endfor -%}
{% endif %}

"""
# CACHE_PEER_LINE = "cache_peer {peer} parent {port} 0 no-query originserver"


class SquidIngressCacheCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(
            squid_pebble_ready=False,
        )
        self.ingress_proxy_provides = IngressProxyProvides(
            self
        )
        self.ingress_cache_provides = IngressCacheProvides(
            self
        )
        self.ingress = IngressRequires(
            self,
            self._get_ingress_config(),
        )

        # Register event handlers.
        self.framework.observe(
            self.on.squid_pebble_ready,
            self._squid_pebble_ready)
        self.framework.observe(
            self.on["ingress"].relation_changed,
            self._ingress_available)
        self.framework.observe(
            self.on["ingress_proxy"].relation_changed,
            self._ingress_proxy_available)
        self.framework.observe(
            self.on["ingress_cache"].relation_changed,
            self._ingress_cache_available)

    def _squid_pebble_ready(self, event):
        self._stored.squid_pebble_ready = True
        self._configure_charm(event)

    def _ingress_proxy_available(self, event):
        self._configure_charm(event)

    def _ingress_cache_available(self, event):
        self._configure_charm(event)

    def _ingress_available(self, event):
        self._configure_charm(event)

    def _ingress_proxy_relation_ready(self):
        ingress_proxy_relation = self.ingress_proxy_provides.get_relation()
        if not ingress_proxy_relation:
            self.unit.status = BlockedStatus(
                'Ingress proxy relation missing')
            return False
        if not self.ingress_proxy_provides.get_complete_relation():
            self.unit.status = BlockedStatus(
                'Ingress proxy relation incomplete')
            return False
        return True

    def _configure_charm(self, event):
        if not self._stored.squid_pebble_ready:
            self.unit.status = BlockedStatus('Pebble not ready')
            return
        if not self._ingress_proxy_relation_ready():
            return
        self._render_config()
        self._configure_pebble(event)
        self.ingress.update_config(self._get_ingress_config())
        self.unit.status = ActiveStatus()

    def _get_squid_config(self):
        jinja_env = jinja2.Environment(loader=jinja2.BaseLoader())
        jinja_template = jinja_env.from_string(SQUID_TEMPLATE)
        ingress_config = self._get_ingress_config()
        squid_config = self._get_squid_config_from_relation()
        ctxt = {
            'port': ingress_config['service-port'],
            'peers': self._get_cache_peers()}
        ctxt.update(squid_config)
        ctxt = {k.replace('-', '_'): v for k, v in ctxt.items()}
        return jinja_template.render(**ctxt)

    def _render_config(self):
        squid_config = self._get_squid_config()
        logger.info("Pushing new squid.conf")
        logger.info(squid_config)
        container = self.unit.get_container("squid")
        # XXX This try/except is to handle the fact that push is not
        #     implemented in the test hareess yet.
        try:
            container.push("/etc/squid/squid.conf", squid_config)
        except NotImplementedError:
            logger.error("Could not push /etc/squid/squid.conf to container")

    def _configure_pebble(self, event):
        """Define and start a workload using the Pebble API.

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        # Get a reference the container attribute on the PebbleReadyEvent
        container = self.unit.get_container("squid")
        existing_plan = container.get_plan().to_dict()
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "squid layer",
            "description": "pebble config layer for squid",
            "services": {
                "squid": {
                    "override": "replace",
                    "summary": "squid service",
                    "command": "/usr/sbin/squid -N",
                    "startup": "enabled",
                }
            },
        }
        if existing_plan.get('services') != pebble_layer['services']:
            # Add intial Pebble config layer using the Pebble API
            container.add_layer("squid", pebble_layer, combine=True)
            # Autostart any services that were defined with startup: enabled
            container.autostart()
            # Learn more about statuses in the SDK docs:
            # https://juju.is/docs/sdk/constructs#heading--statuses
            # self._advertise_ingress_info()

    def _client_relation(self):
        if self.ingress_proxy_provides.get_complete_relation():
            return self.ingress_proxy_provides
        if self.ingress_cache_provides.get_complete_relation():
            return self.ingress_cache_provides

    def _get_ingress_config(self):
        default_ingress_config = {
            "service-hostname": self.app.name,
            "service-name": self.app.name,
            "service-port": 3128,
        }
        relation = self._client_relation()
        if relation:
            return relation.get_ingress_data()
        else:
            return default_ingress_config

    def _get_squid_config_from_relation(self):
        if self.ingress_cache_provides.get_complete_relation():
            relation = self._client_relation()
            return relation.get_cache_data()
        return {}

    def _ingress_proxy_relation_changed(self, event):
        self.ingress.update_config(self.get_ingress_config())

    def _get_cache_peers(self, domain="svc.cluster.local"):
        relation = self._client_relation().get_relation()
        cache_peers = []
        svc_name = relation.data[relation.app]["service-name"]
        for peer in relation.units:
            unit_name = peer.name.replace('/', '-')
            cache_peers.append(
                f"{unit_name}.{svc_name}-endpoints.{self.model.name}.{domain}")
        return cache_peers


if __name__ == "__main__":
    main(SquidIngressCacheCharm)

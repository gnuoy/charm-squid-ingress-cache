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
from ops.model import ActiveStatus
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

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
#http_port 3128 accel
coredump_dir /var/spool/squid
refresh_pattern ^ftp:		1440	20%	10080
refresh_pattern ^gopher:	1440	0%	1440
refresh_pattern -i (/cgi-bin/|\?) 0	0%	0
refresh_pattern \/(Packages|Sources)(|\.bz2|\.gz|\.xz)$ 0 0% 0 refresh-ims
refresh_pattern \/Release(|\.gpg)$ 0 0% 0 refresh-ims
refresh_pattern \/InRelease$ 0 0% 0 refresh-ims
refresh_pattern \/(Translation-.*)(|\.bz2|\.gz|\.xz)$ 0 0% 0 refresh-ims
refresh_pattern .		0	20%	4320
"""

class SquidCacheCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.squid_pebble_ready, self._on_squid_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
#        self.framework.observe(self.on.fortune_action, self._on_fortune_action)
        self.framework.observe(self.on.ingress_relation_joined, self._ingress_relation_joined)
        self._stored.set_default(things=[])
        self.ingress = None
        # XXX Remove self._advertise_ingress_info
        self._advertise_ingress_info()

    def _update_files(self):
        container = self.unit.get_container("squid")
        relation = self.model.get_relation("cache")
        hostname = relation.data[relation.app]["service-hostname"]
        svc_name = relation.data[relation.app]["service-name"]
        port = relation.data[relation.app]["service-port"]
        squid_template = SQUID_TEMPLATE + f"http_port {port} accel\n"
        cache_peers = [u.name.replace('/', '-') for u in relation.units]
        for peer in cache_peers:
            peer_fqdn = f"{peer}.{svc_name}-endpoints.{self.model.name}.svc.cluster.local"
            logger.error("Appending for {}".format(peer_fqdn))
            squid_template = squid_template + f"cache_peer {peer_fqdn} parent {port} 0 no-query originserver"
        logger.error("Pushing new squid.conf")
        logger.error(squid_template)
        container.push("/etc/squid/squid.conf", squid_template)

    def _on_squid_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        TEMPLATE-TODO: change this example to suit your needs.
        You'll need to specify the right entrypoint and environment
        configuration for your specific workload. Tip: you can see the
        standard entrypoint of an existing container using docker inspect

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        self._update_files()
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
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
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("squid", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self._advertise_ingress_info()

    def _advertise_ingress_info(self):
        ingress_relation = self.model.get_relation("ingress")
        cache_relation = self.model.get_relation("cache")
        if ingress_relation and cache_relation:
            ingress_config = {
                "service-hostname": cache_relation.data[cache_relation.app].get("service-hostname", "dummy"),
                "service-name": self.app.name,
                "service-port": cache_relation.data[cache_relation.app].get("service-port", "80"),
            }
            if self.ingress:
                self.ingress.update_config(ingress_config)
            else:
                self.ingress = IngressRequires(
                    self, 
                    ingress_config,
                )

    def _ingress_relation_joined(self, _):
        self._advertise_ingress_info()

    def _on_config_changed(self, _):
        """Just an example to show how to deal with changed configuration.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle config, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the config.py file.

        Learn more about config at https://juju.is/docs/sdk/config
        """
        self._advertise_ingress_info()
#        current = self.config["thing"]
#        if current not in self._stored.things:
#            logger.debug("found a new thing: %r", current)
#            self._stored.things.append(current)
#
#    def _on_fortune_action(self, event):
#        """Just an example to show how to receive actions.
#
#        TEMPLATE-TODO: change this example to suit your needs.
#        If you don't need to handle actions, you can remove this method,
#        the hook created in __init__.py for it, the corresponding test,
#        and the actions.py file.
#
#        Learn more about actions at https://juju.is/docs/sdk/actions
#        """
#        fail = event.params["fail"]
#        if fail:
#            event.fail(fail)
#        else:
#            event.set_results({"fortune": "A bug in the code is worth two in the documentation."})


if __name__ == "__main__":
    main(SquidCacheCharm)
